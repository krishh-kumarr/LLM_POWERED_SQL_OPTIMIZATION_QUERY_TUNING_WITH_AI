#!/bin/bash

# AI SQL Copilot - Frontend Setup Script
# This script sets up the React frontend environment

echo "🚀 AI SQL Copilot - Frontend Setup"
echo "==================================="
echo ""

# Check Node.js version
echo "📋 Checking Node.js version..."
node --version

if [ $? -ne 0 ]; then
    echo "❌ Node.js is not installed. Please install Node.js 18 or higher."
    exit 1
fi

echo ""

# Check npm version
echo "📋 Checking npm version..."
npm --version

if [ $? -ne 0 ]; then
    echo "❌ npm is not installed."
    exit 1
fi

echo ""

# Install dependencies
echo "📦 Installing Node.js dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies."
    exit 1
fi

echo "✅ Dependencies installed successfully"
echo ""
echo "✅ Frontend setup complete!"
echo ""
echo "To start the development server:"
echo "  npm run dev"
echo ""
echo "The app will be available at: http://localhost:5173"
