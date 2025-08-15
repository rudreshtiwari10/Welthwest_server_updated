#!/bin/bash
# Production startup script for Render

echo "Starting production server with model compatibility checks..."

# Check if we're in production
if [ "$FLASK_ENV" = "production" ] || [ -n "$RENDER" ]; then
    echo "Production environment detected"
    
    # Remove any incompatible model files
    if [ -f "market_regime_model.pkl" ]; then
        echo "Removing potentially incompatible model file..."
        mv market_regime_model.pkl market_regime_model.pkl.backup
        echo "Model file backed up and removed"
    fi
    
    echo "Model will be retrained automatically on first use"
else
    echo "Development environment detected"
fi

# Start the application
echo "Starting Flask application..."
python app.py
