#!/bin/bash

# PDF PayPal System Web Application - GCP Deployment Script
# This script helps third parties deploy the web application to Google Cloud Platform

set -e

echo "=== PDF PayPal System Web Application - GCP Deployment ==="
echo

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install Google Cloud SDK first."
    echo "   Download from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if user is logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ You are not logged in to gcloud."
    echo "   Please run: gcloud auth login"
    exit 1
fi

# Get current project
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ No GCP project is set."
    echo "   Please run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "📋 Current GCP Project: $PROJECT_ID"
echo

# Prompt for confirmation
read -p "Deploy PDF PayPal System Web Application to project '$PROJECT_ID'? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled."
    exit 1
fi

echo "🚀 Starting deployment..."
echo

# Enable required APIs
echo "📡 Enabling required Google Cloud APIs..."
gcloud services enable appengine.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Create App Engine app if it doesn't exist
if ! gcloud app describe &> /dev/null; then
    echo "🏗️  Creating App Engine application..."
    # Prompt for region
    echo "Available regions for App Engine:"
    echo "  us-central1 (Iowa)"
    echo "  us-east1 (South Carolina)" 
    echo "  europe-west1 (Belgium)"
    echo "  asia-northeast1 (Tokyo)"
    echo "  asia-southeast1 (Singapore)"
    echo
    read -p "Enter region (default: us-central1): " REGION
    REGION=${REGION:-us-central1}
    
    gcloud app create --region=$REGION
fi

# Copy webapp files to temporary deployment directory
echo "📦 Preparing deployment files..."
DEPLOY_DIR="webapp_deploy_$(date +%Y%m%d_%H%M%S)"
mkdir -p $DEPLOY_DIR

# Copy essential files
cp webapp.py $DEPLOY_DIR/main.py  # App Engine expects main.py
cp webapp.yaml $DEPLOY_DIR/app.yaml  # App Engine expects app.yaml
cp requirements-webapp.txt $DEPLOY_DIR/requirements.txt
cp webapp_extractors.py $DEPLOY_DIR/
cp -r templates $DEPLOY_DIR/

# Create uploads directory
mkdir -p $DEPLOY_DIR/uploads

echo "✅ Deployment files prepared in $DEPLOY_DIR/"
echo

# Deploy to App Engine
echo "🚀 Deploying to Google App Engine..."
cd $DEPLOY_DIR
gcloud app deploy app.yaml --quiet

# Get the deployed URL
APP_URL=$(gcloud app browse --no-launch-browser)

echo
echo "🎉 Deployment completed successfully!"
echo
echo "📱 Your PDF PayPal System Web Application is now live at:"
echo "   $APP_URL"
echo
echo "🛠️  Next steps:"
echo "   1. Visit the application URL above"
echo "   2. Go to Settings page and configure your PayPal API credentials"
echo "   3. Test the connection and start processing PDFs!"
echo
echo "💡 Tips:"
echo "   - Use PayPal Sandbox credentials for testing"
echo "   - Switch to Live mode only when ready for production"
echo "   - Keep your API credentials secure"
echo

# Cleanup
cd ..
read -p "Clean up deployment files in $DEPLOY_DIR? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    rm -rf $DEPLOY_DIR
    echo "🧹 Deployment files cleaned up."
fi

echo "✅ Deployment script completed!"