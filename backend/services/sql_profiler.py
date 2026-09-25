"""
Prism SQLProfiler (merged, streaming-safe, heuristic network time)

Drop-in replacement for previous profiler. Uses db_connection for execution.

Full-featured SQL profiler:
  - DB-side timing via EXPLAIN ANALYZE for read-only queries (safe option)
  - CPU measurement (raw, per-core normalized, cpu-seconds) — measured on the client process (psutil)
  - Wall time median over repeats (client-side)
  - Fetch vs conversion timing
  - Streaming mode (no full materialization) and sampled memory estimation
  - pympler deep-size when available, otherwise JSON/repr sample estimate

IMPORTANT NOTES:
  - DB execution time (db_execution_time_ms) is attempted via EXPLAIN ANALYZE and is authoritative
    for server-side execution work when available. This may execute the query on the server (read-only
    only by default).
  - CPU and memory metrics reported here are measured on the client process by default:
      - cpu_* fields derive from psutil measurements of the client process.
      - memory_used_mb is an estimate extrapolated from sampled rows (or pympler when available),
        and reflects client-side memory footprint for the result set, not the DB server's internal
        buffers, temp files, or OS page cache.
  - network_time_ms is heuristic: fetch_time_ms - db_execution_time_ms when both measurements exist.
"""

import time
import psutil
import logging
import re
import json
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

try:
    from pympler import asizeof
    _HAS_PYML = True
except Exception:
    _HAS_PYML = False

# optional parser for slightly better read-only detection
try:
    import sqlparse  # type: ignore
    _HAS_SQLPARSE = True
except Exception:
    _HAS_SQLPARSE = False

from models.db_connection import db_connection


class SQLProfiler:
    """
    Full-featured SQL profiler.

    See module docstring for notes about sources and limitations.
    """

    def __init__(
        self,
        repeat: int = 3,
        sample_rows_for_memory: int = 100,
        max_return_rows: int = 1000,
        measure_overhead: bool = True,
        allow_db_timing_on_non_select: bool = False,
        stream_default: bool = False,
        stream_sample_every: int = 10,
    ):
        """
        :param repeat: how many times to execute query for CPU/wall median (warning: runs query that many times)
        :param sample_rows_for_memory: rows to sample for memory estimation when result is large
        :param max_return_rows: limit rows returned in 'data' field
        :param measure_overhead: measure internal instrumentation overhead at init (small time cost)
        :param allow_db_timing_on_non_select: if True, run EXPLAIN ANALYZE even on non-SELECT (dangerous)
        :param stream_default: default streaming behavior for profile_query if not specified
        :param stream_sample_every: sample every N rows when streaming
        """
        self.process = psutil.Process()
        self.repeat = max(1, int(repeat))
        self.sample_rows_for_memory = max(1, int(sample_rows_for_memory))
        self.max_return_rows = max(1, int(max_return_rows))
        self.allow_db_timing_on_non_select = bool(allow_db_timing_on_non_select)
        self.stream_default = bool(stream_default)
        self.stream_sample_every = max(1, int(stream_sample_every))

        # measure instrumentation overhead (median)
        self.instrumentation_overhead_s = 0.0
        if measure_overhead:
            try:
                self.instrumentation_overhead_s = self._measure_instrumentation_overhead(iterations=7)
                logger.debug("Instrumentation overhead (s): %.6f", self.instrumentation_overhead_s)
            except Exception:
                self.instrumentation_overhead_s = 0.0

    # ---------------- utilities ----------------
    def _is_read_only_query(self, query: str) -> bool:
        """
        Conservative check: True for SELECT/WITH/EXPLAIN/SHOW/PRAGMA/DESCRIBE
        Uses sqlparse if available for slightly better parsing; falls back to regex-first-word.
        Improved: strips leading comments and parentheses before checking.
        """
        if not query:
            return False

        # normalize and remove leading comments and block comments
        q = str(query).strip()
        # remove leading single-line comments
        q = re.sub(r'^(?:\s*--[^\n]*\n)+', '', q)
        # remove leading block comments
        q = re.sub(r'^\s*/\*.*?\*/\s*', '', q, flags=re.DOTALL)
        # strip leading parentheses (e.g., "(SELECT ...)")
        q = q.lstrip('(').strip()
        if not q:
            return False

        if _HAS_SQLPARSE:
            try:
                parsed = sqlparse.parse(q)
                if parsed:
                    # find first meaningful token text
                    first_token = None
                    for t in parsed[0].tokens:
                        if not t.is_whitespace and t.value.strip() != "":
                            first_token = t.value.strip().lower()
                            break
                    if first_token:
                        return first_token.split()[0] in ("select", "with", "explain", "show", "describe", "pragma")
            except Exception:
                # fall back to regex
                pass

        # fallback: regex first word
        m = re.match(r'^\s*([a-z]+)', q.lower())
        if not m:
            return False
        return m.group(1) in ("select", "with", "explain", "show", "describe", "pragma")

    def _measure_instrumentation_overhead(self, iterations: int = 5) -> float:
        """
        Measure median overhead of calling the CPU timing wrapper around a noop.
        Returns median seconds.
        """
        times = []
        for _ in range(max(1, iterations)):
            try:
                t0 = time.perf_counter()
                # baseline instrumentation: cpu times read
                _ = self.process.cpu_times()
                t1 = time.perf_counter()
                times.append(t1 - t0)
            except Exception:
                pass
        if not times:
            return 0.0
        times.sort()
        return times[len(times) // 2]

    # ---------------- CPU measurement ----------------
    def _measure_cpu_during_execution(self, query_func) -> Tuple[float, float, float, float, Any]:
        """
        Execute query_func and measure:
          - raw_cpu_percent (may be >100 on multi-core)
          - cpu_per_core_percent (normalized <= 100)
          - wall_elapsed_seconds (wall time minus overhead, clamped)
          - cpu_seconds_used (user+system delta seconds)
          - db_result (returned object)

        NOTE: These CPU numbers are computed from the client process' cpu_times (psutil).
        They represent client-side CPU usage (serialization/conversion/fetch), not DB server CPU.
        """
        cpu_before = self.process.cpu_times()
        cpu_before_total = cpu_before.user + cpu_before.system

        wall_start = time.perf_counter()
        result = query_func()
        wall_end = time.perf_counter()

        cpu_after = self.process.cpu_times()
        cpu_after_total = cpu_after.user + cpu_after.system

        raw_wall = wall_end - wall_start
        # subtract measured overhead only when it is smaller than the raw measurement; otherwise keep raw
        if self.instrumentation_overhead_s and raw_wall > self.instrumentation_overhead_s:
            wall_elapsed = raw_wall - self.instrumentation_overhead_s
        else:
            wall_elapsed = raw_wall
            if self.instrumentation_overhead_s and raw_wall <= self.instrumentation_overhead_s:
                logger.debug(
                    "Instrumentation overhead (%.6fs) >= raw wall (%.6fs); not subtracting.",
                    self.instrumentation_overhead_s, raw_wall
                )
        wall_elapsed = max(wall_elapsed, 1e-9)

        cpu_seconds_used = max(cpu_after_total - cpu_before_total, 0.0)
        raw_cpu_percent = (cpu_seconds_used / wall_elapsed) * 100.0 if wall_elapsed > 0 else 0.0

        cores = psutil.cpu_count(logical=True) or 1
        cpu_per_core_percent = raw_cpu_percent / cores
        cpu_per_core_percent = max(0.0, min(100.0, cpu_per_core_percent))

        return (
            round(raw_cpu_percent, 2),
            round(cpu_per_core_percent, 2),
            round(wall_elapsed, 6),
            round(cpu_seconds_used, 6),
            result,
        )

    # ---------------- memory estimation ----------------
    def _calculate_memory_usage(
        self,
        sample_rows: List[Any],
        columns: List[str],
        total_rows: int,
    ) -> Dict[str, Any]:
        """
        Estimate memory used by the FULL result set, using a sample.

        Returns dict:
          {'memory_used_mb': float, 'method': str}

        The returned memory estimate describes client-side memory for the result (serialized / Python objects).
        It does not represent DB server memory (sort buffers, temp files, shared buffers).
        """
        if total_rows <= 0 or not sample_rows:
            return {"memory_used_mb": 0.0, "method": "none"}

        try:
            n_sample = len(sample_rows)
            n_total = total_rows

            # If the total result is small, treat the sample as the full set
            if _HAS_PYML and n_total <= self.sample_rows_for_memory:
                total_bytes = asizeof.asizeof(sample_rows)
                if columns:
                    total_bytes += asizeof.asizeof(columns)
                return {
                    "memory_used_mb": total_bytes / 1024.0 / 1024.0,
                    "method": "pympler_full",
                }

            # Larger result: extrapolate from sample
            if _HAS_PYML:
                sample_bytes = asizeof.asizeof(sample_rows)
                avg_per_row = sample_bytes / float(n_sample)
                estimated_total = avg_per_row * n_total
                if columns:
                    estimated_total += asizeof.asizeof(columns)
                return {
                    "memory_used_mb": estimated_total / 1024.0 / 1024.0,
                    "method": "pympler_sample",
                }
            else:
                total_sample_bytes = 0
                for row in sample_rows:
                    try:
                        total_sample_bytes += len(json.dumps(row, default=str).encode("utf-8"))
                    except Exception:
                        total_sample_bytes += len(repr(row).encode("utf-8"))

                avg = total_sample_bytes / float(n_sample)
                estimated_total = avg * n_total + len(columns) * 50
                return {
                    "memory_used_mb": estimated_total / 1024.0 / 1024.0,
                    "method": "serialized_sample",
                }

        except Exception as e:
            logger.debug("Memory calc error: %s", e)
            rough = (total_rows * 1024 + len(columns) * 50) / 1024.0 / 1024.0
            return {"memory_used_mb": rough, "method": "fallback"}

    # ---------------- explain/analyze (DB-side) ----------------
    def _explain_analyze_time(self, query: str) -> Optional[float]:
        """
        Get server-side execution time (ms) via EXPLAIN ANALYZE or MySQL profiling.
        WARNING: EXPLAIN ANALYZE often executes the query. Only call if query is read-only
                 or explicitly allowed via allow_db_timing_on_non_select.
        Returns the DB's execution time in milliseconds, or None if not available/parsing failed.
        """
        try:
            from sqlalchemy import text
            db_type = db_connection.db_type

            # strip trailing semicolon which can break EXPLAIN embedding
            q = query.strip()
            if q.endswith(";"):
                q = q[:-1]

            if db_type == "postgresql":
                explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {q}"
                res = None
                try:
                    res = db_connection.connection.execute(text(explain_query))
                    plan_row = res.fetchone()
                    plan_val = plan_row[0] if plan_row and len(plan_row) > 0 else None

                    # plan_val may be JSON string or already a Python object
                    plan_json = None
                    if isinstance(plan_val, str):
                        try:
                            plan_json = json.loads(plan_val)
                        except Exception:
                            try:
                                plan_json = json.loads(plan_val.replace("'", '"'))
                            except Exception:
                                plan_json = None
                    else:
                        plan_json = plan_val

                    # Postgres returns a list with a single JSON object for FORMAT JSON
                    if isinstance(plan_json, list) and plan_json:
                        top = plan_json[0]
                        # the execution time may be under various keys
                        # look for top-level "Execution Time" or under Plan/Execution Time
                        if isinstance(top, dict):
                            if "Execution Time" in top:
                                return float(top["Execution Time"])
                            if "Plan" in top and isinstance(top["Plan"], dict) and "Execution Time" in top["Plan"]:
                                return float(top["Plan"]["Execution Time"])
                    elif isinstance(plan_json, dict):
                        if "Execution Time" in plan_json:
                            return float(plan_json["Execution Time"])
                        if "Plan" in plan_json and isinstance(plan_json["Plan"], dict) and "Execution Time" in plan_json["Plan"]:
                            return float(plan_json["Plan"]["Execution Time"])
                finally:
                    try:
                        if res is not None and hasattr(res, "close"):
                            res.close()
                    except Exception:
                        pass

            elif db_type == "mysql":
                from sqlalchemy import text as sa_text
                # Try EXPLAIN ANALYZE (MySQL 8+), but connector output varies — best-effort only
                try:
                    _ = db_connection.connection.execute(sa_text(f"EXPLAIN ANALYZE {q}"))
                    # Not parsing output here to avoid brittle parsing; leave as None unless fallback works.
                except Exception:
                    pass
                # Fallback: SHOW PROFILES (deprecated in some setups)
                try:
                    db_connection.connection.execute(sa_text("SET profiling = 1"))
                    db_connection.connection.execute(sa_text(q))
                    prof = db_connection.connection.execute(sa_text("SHOW PROFILES")).fetchall()
                    if prof:
                        # SHOW PROFILES returns seconds in second column; convert to ms
                        return float(prof[-1][1]) * 1000.0
                except Exception:
                    pass

            return None
        except Exception as e:
            logger.debug("Explain analyze failed: %s", e)
            return None

    # ---------------- main profiling API ----------------
    def profile_query(self, query: str, stream: Optional[bool] = None) -> Dict[str, Any]:
        """
        Profile a SQL query and return a dictionary of metrics and preview results.

        :param query: SQL string
        :param stream: If True, do true streaming: avoid building full data in memory; return only preview rows.
                       If None, uses self.stream_default.
        """
        if not db_connection.connection:
            return {"success": False, "message": "No active database connection"}

        if stream is None:
            stream = self.stream_default

        try:
            from sqlalchemy import text

            # Only attempt DB-side timing for read-only queries unless allow_db_timing_on_non_select=True
            if self.allow_db_timing_on_non_select or self._is_read_only_query(query):
                db_execution_time_ms = self._explain_analyze_time(query)
            else:
                db_execution_time_ms = None
            use_db_timing = db_execution_time_ms is not None

            def _exec_cursor():
                # Try to enable streaming if supported by SQLAlchemy/dialect
                try:
                    return db_connection.connection.execution_options(stream_results=True).execute(text(query))
                except Exception:
                    return db_connection.connection.execute(text(query))

            # Repeat measurement loop (this will execute the query self.repeat times)
            measurements = []
            last_cursor = None
            for _ in range(self.repeat):
                raw_pct, norm_pct, wall_elapsed, cpu_seconds, cursor = self._measure_cpu_during_execution(_exec_cursor)
                measurements.append(
                    {"raw": raw_pct, "norm": norm_pct, "wall": wall_elapsed, "cpu_seconds": cpu_seconds}
                )
                last_cursor = cursor

            if last_cursor is None:
                raise Exception("Query execution failed during measurement")

            raw_vals = sorted(m["raw"] for m in measurements)
            norm_vals = sorted(m["norm"] for m in measurements)
            wall_vals = sorted(m["wall"] for m in measurements)
            cpu_seconds_vals = sorted(m["cpu_seconds"] for m in measurements)

            cpu_raw = raw_vals[len(raw_vals) // 2]
            cpu_norm = norm_vals[len(norm_vals) // 2]
            wall_median = wall_vals[len(wall_vals) // 2]
            cpu_seconds_used = cpu_seconds_vals[len(cpu_seconds_vals) // 2]

            cursor = last_cursor

            # Fetch vs convert: support streaming mode that does not materialize full dataset
            fetch_start = time.perf_counter()
            data_preview: List[Dict[str, Any]] = []
            columns: List[str] = []
            row_count = 0
            fetch_time_ms = 0.0
            conversion_time_ms = 0.0
            memory_used_mb = 0.0
            memory_method = "none"

            try:
                if getattr(cursor, "returns_rows", False):
                    # Streaming-aware iteration: sample rows for memory estimation and collect preview rows
                    rows_for_preview = []
                    sampled_rows_for_memory = []
                    sample_every = self.stream_sample_every
                    preview_limit = self.max_return_rows

                    # Try chunked fetch if available
                    try:
                        if hasattr(cursor, "fetchmany"):
                            chunk_size = 1000
                            count = 0
                            while True:
                                chunk = cursor.fetchmany(chunk_size)
                                if not chunk:
                                    break
                                for row in chunk:
                                    count += 1
                                    # sample for memory
                                    if len(sampled_rows_for_memory) < self.sample_rows_for_memory and (
                                        count % sample_every == 0
                                    ):
                                        sampled_rows_for_memory.append(row)
                                    # preview rows collection
                                    if len(rows_for_preview) < preview_limit:
                                        rows_for_preview.append(row)
                            row_count = count
                        else:
                            # fallback: iterate cursor
                            count = 0
                            for row in cursor:
                                count += 1
                                if len(sampled_rows_for_memory) < self.sample_rows_for_memory and (
                                    count % sample_every == 0
                                ):
                                        sampled_rows_for_memory.append(row)
                                if len(rows_for_preview) < preview_limit:
                                        rows_for_preview.append(row)
                            row_count = count
                    except Exception:
                        # worst-case fallback to fetchall (may materialize large set)
                        try:
                            rows_full = cursor.fetchall()
                        except Exception:
                            rows_full = []
                        row_count = len(rows_full)
                        rows_for_preview = rows_full[:preview_limit]
                        sampled_rows_for_memory = rows_full[: self.sample_rows_for_memory]

                    # determine columns if possible (cursor.keys())
                    try:
                        columns = list(cursor.keys()) if hasattr(cursor, "keys") else []
                    except Exception:
                        columns = []

                    fetch_end = time.perf_counter()
                    fetch_time_ms = (fetch_end - fetch_start) * 1000.0

                    # Convert preview rows to dicts for returning
                    conv_start = time.perf_counter()
                    for row in rows_for_preview:
                        try:
                            # Prefer SQLAlchemy Row._mapping when available (provides mapping of column->value)
                            if hasattr(row, "_mapping"):
                                # row._mapping is dict-like; create a shallow dict
                                data_preview.append(dict(row._mapping))
                            elif columns and len(columns) == len(row):
                                data_preview.append(dict(zip(columns, row)))
                            else:
                                data_preview.append({str(i): row[i] for i in range(len(row))})
                        except Exception:
                            # fallback
                            try:
                                data_preview.append(dict(zip(columns, row)))
                            except Exception:
                                data_preview.append({str(i): row[i] for i in range(len(row))})
                    conv_end = time.perf_counter()
                    conversion_time_ms = (conv_end - conv_start) * 1000.0

                    # Memory estimation: operate on sampled_rows_for_memory (converted as needed),
                    # and extrapolate to full row_count
                    sample_converted = []
                    for row in sampled_rows_for_memory:
                        if hasattr(row, "_mapping"):
                            sample_converted.append(dict(row._mapping))
                        elif columns and len(columns) == len(row):
                            sample_converted.append(dict(zip(columns, row)))
                        else:
                            sample_converted.append({str(i): row[i] for i in range(len(row))})

                    mem_info = self._calculate_memory_usage(
                        sample_converted,
                        columns,
                        total_rows=row_count,
                    )
                    memory_used_mb = round(mem_info.get("memory_used_mb", 0.0), 4)
                    memory_method = mem_info.get("method", "unknown")

                else:
                    # Non-select
                    fetch_end = time.perf_counter()
                    fetch_time_ms = (fetch_end - fetch_start) * 1000.0
                    try:
                        row_count = int(cursor.rowcount) if cursor.rowcount is not None else 0
                    except Exception:
                        row_count = 0
                    data_preview = []
                    columns = []
                    conversion_time_ms = 0.0
                    memory_used_mb = 0.0
                    memory_method = "none"

            finally:
                # close result/cursor if possible to release DB resources
                try:
                    if hasattr(cursor, "close"):
                        cursor.close()
                    elif hasattr(cursor, "cursor") and hasattr(cursor.cursor, "close"):
                        cursor.cursor.close()
                except Exception:
                    pass

            # If DB timing not available, approximate using median wall time
            if not use_db_timing:
                db_execution_time_ms = round(wall_median * 1000.0, 2)

            # Total time: DB execution + fetch + conversion
            total_time_ms = round(
                (db_execution_time_ms or 0.0) + fetch_time_ms + conversion_time_ms,
                2,
            )

            # network_time heuristic (approximate)
            network_time_ms = None
            network_time_is_heuristic = False
            try:
                if db_execution_time_ms is not None:
                    # fetch_time_ms is ms, db_execution_time_ms is ms -> subtract
                    network_time_ms = max(0.0, round(fetch_time_ms - db_execution_time_ms, 2))
                    network_time_is_heuristic = True
            except Exception:
                network_time_ms = None
                network_time_is_heuristic = False

            # Truncate preview data if needed (it is already preview-limited)
            truncated = False
            data_to_return = data_preview
            if row_count > self.max_return_rows:
                truncated = True

            # query plan (best-effort)
            try:
                qp_resp = db_connection.get_query_plan(query)
                query_plan = qp_resp.get("plan", []) if qp_resp and qp_resp.get("success") else []
            except Exception:
                query_plan = []

            # Provide clear provenance for timing/memory/cpu metrics
            timing_source = "database" if use_db_timing else "python"
            db_timing_source = "explain_analyze" if use_db_timing else None
            cpu_timing_source = "client_process_psutil"
            memory_timing_source = memory_method  # already conveys pympler vs serialized_sample vs fallback

            result = {
                "success": True,
                "query": query,
                "db_execution_time_ms": round(db_execution_time_ms, 2) if db_execution_time_ms is not None else None,
                "db_timing_source": db_timing_source,
                "fetch_time_ms": round(fetch_time_ms, 2),
                "conversion_time_ms": round(conversion_time_ms, 2),
                "total_time_ms": total_time_ms,
                "network_time_ms": network_time_ms,
                "network_time_is_heuristic": network_time_is_heuristic,
                "memory_used_mb": memory_used_mb,
                "memory_calculation_method": memory_method,
                "cpu_raw_percent": cpu_raw,
                "cpu_per_core_percent": cpu_norm,
                "cpu_seconds_used": cpu_seconds_used,
                "cpu_timing_source": cpu_timing_source,
                "wall_elapsed_seconds_median": round(wall_median, 6),
                "row_count": row_count,
                "columns": columns,
                "data": data_to_return,
                "data_truncated": truncated,
                "timing_source": timing_source,
                "memory_timing_source": memory_timing_source,
                "query_plan": query_plan,
            }

            # Backward compatibility: Add aliases for existing code
            result["execution_time_ms"] = total_time_ms  # Alias for total_time_ms
            result["cpu_percent"] = cpu_norm  # Use normalized CPU percent (per-core)

            logger.info(
                "Profiled query rows=%d db=%.2fms fetch=%.2fms conv=%.2fms total=%.2fms mem=%.4fMB mem_method=%s cpu_raw=%.2f cpu_per_core=%.2f trunc=%s",
                row_count,
                db_execution_time_ms or 0.0,
                fetch_time_ms,
                conversion_time_ms,
                total_time_ms,
                memory_used_mb,
                memory_method,
                cpu_raw,
                cpu_norm,
                truncated,
            )

            return result

        except Exception as e:
            logger.exception("Error profiling query: %s", e)
            return {"success": False, "message": f"Query profiling failed: {str(e)}"}

    # ---------------- comparison helper ----------------
    def compare_queries(self, original_query: str, optimized_query: str) -> Dict[str, Any]:
        """
        Compare original vs optimized query based on profiler metrics.

        NOTE: We intentionally do NOT use memory deltas for "better/worse" decisions now.
        We only compare time, but still pass through memory_used_mb for display if needed.
        """
        try:
            logger.info("Profiling original query...")
            original_result = self.profile_query(original_query)

            logger.info("Profiling optimized query...")
            optimized_result = self.profile_query(optimized_query)

            if not original_result.get("success") or not optimized_result.get("success"):
                return {
                    "success": False,
                    "message": "Failed to profile one or both queries",
                    "original_result": original_result,
                    "optimized_result": optimized_result,
                }

            # Time metrics
            orig_time = original_result.get("total_time_ms", original_result.get("execution_time_ms", 0.0))
            opt_time = optimized_result.get("total_time_ms", optimized_result.get("execution_time_ms", 0.0))
            time_improvement = orig_time - opt_time  # positive => optimized is faster
            time_improvement_percent = (time_improvement / orig_time * 100.0) if orig_time > 0 else 0.0
            is_faster = time_improvement > 0

            comparison = {
                "success": True,
                "original": {
                    "query": original_query,
                    "total_time_ms": orig_time,
                    "db_execution_time_ms": original_result.get("db_execution_time_ms"),
                    "fetch_time_ms": original_result.get("fetch_time_ms"),
                    "conversion_time_ms": original_result.get("conversion_time_ms"),
                    "memory_used_mb": original_result.get("memory_used_mb", 0.0),
                    "cpu_raw_percent": original_result.get("cpu_raw_percent", 0.0),
                    "cpu_per_core_percent": original_result.get("cpu_per_core_percent", 0.0),
                    "cpu_percent": original_result.get("cpu_percent", 0.0),  # Backward compat
                    "row_count": original_result.get("row_count", 0),
                    "db_timing_source": original_result.get("db_timing_source"),
                    "memory_timing_source": original_result.get("memory_timing_source"),
                    "query_plan": original_result.get("query_plan", []),
                },
                "optimized": {
                    "query": optimized_query,
                    "total_time_ms": opt_time,
                    "db_execution_time_ms": optimized_result.get("db_execution_time_ms"),
                    "fetch_time_ms": optimized_result.get("fetch_time_ms"),
                    "conversion_time_ms": optimized_result.get("conversion_time_ms"),
                    "memory_used_mb": optimized_result.get("memory_used_mb", 0.0),
                    "cpu_raw_percent": optimized_result.get("cpu_raw_percent", 0.0),
                    "cpu_per_core_percent": optimized_result.get("cpu_per_core_percent", 0.0),
                    "cpu_percent": optimized_result.get("cpu_percent", 0.0),  # Backward compat
                    "row_count": optimized_result.get("row_count", 0),
                    "db_timing_source": optimized_result.get("db_timing_source"),
                    "memory_timing_source": optimized_result.get("memory_timing_source"),
                    "query_plan": optimized_result.get("query_plan", []),
                },
                # Keep nested structure for time-only improvements
                "improvements": {
                    "time_saved_ms": round(time_improvement, 2),
                    "time_improvement_percent": round(time_improvement_percent, 2),
                    "is_faster": is_faster,
                },
                # Flat fields for convenience (time only)
                "time_improvement_ms": round(time_improvement, 2),
                "time_improvement_percent": round(time_improvement_percent, 2),
                "is_faster": is_faster,
                # Optimized preview data / columns
                "data": optimized_result.get("data", []),
                "columns": optimized_result.get("columns", []),
            }

            logger.info(
                "Query comparison done: %.2f%% time improvement (Δ=%.2f ms)",
                time_improvement_percent,
                time_improvement,
            )
            return comparison

        except Exception as e:
            logger.exception("Error comparing queries")
            return {"success": False, "message": f"Query comparison failed: {str(e)}"}

    # ---------------- system metrics ----------------
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Returns host-level system metrics (useful for host monitoring).
        These are sampled on the client host running this profiler and do not reflect remote DB host unless running locally.
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "success": True,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available / 1024 / 1024,
                "memory_used_mb": memory.used / 1024 / 1024,
                "disk_percent": disk.percent,
            }
        except Exception as e:
            logger.exception("Error getting system metrics")
            return {"success": False, "message": f"Failed to get system metrics: {str(e)}"}


# Global profiler instance with default settings (single run for speed, can be customized)
sql_profiler = SQLProfiler(repeat=1)  # Use repeat=1 for faster execution by default
