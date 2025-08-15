#!/usr/bin/env python3
"""
Script to add production compatibility methods to market_regime_classifier.py
"""

def add_production_methods():
    """Add production compatibility methods to the classifier"""
    
    # Read the current file
    with open('services/market_regime_classifier.py', 'r') as f:
        content = f.read()
    
    # Find the position to insert the new methods (after check_model_compatibility)
    insert_position = content.find('# Helper methods for feature calculation')
    
    if insert_position == -1:
        print("❌ Could not find insertion point")
        return False
    
    # Production compatibility methods to add
    production_methods = '''
    def force_retrain_for_production(self):
        """Force retrain the model for production compatibility"""
        try:
            logger.info("Forcing model retrain for production compatibility")
            
            # Reset model state
            self.is_trained = False
            self.feature_names = []
            
            # Create new model instance
            self.model = RandomForestClassifier(
                n_estimators=100,
                criterion='gini',
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1
            )
            
            # Reset scaler
            self.scaler = StandardScaler()
            
            logger.info("Model reset completed. Ready for retraining.")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting model: {str(e)}")
            return False
    
    def handle_production_compatibility(self):
        """Handle production compatibility issues automatically"""
        try:
            # Check if we're in production
            is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER')
            
            if is_production:
                logger.info("Running in production environment - checking compatibility")
                
                # Try to load existing model
                try:
                    self.load_model()
                    
                    # Test compatibility
                    compatibility = self.check_model_compatibility()
                    
                    if not compatibility.get("compatible", False):
                        logger.warning("Model compatibility issue detected in production")
                        logger.info("Forcing model retrain for production compatibility")
                        
                        # Force retrain
                        if self.force_retrain_for_production():
                            logger.info("Model reset successful. Will be retrained on first use.")
                            return True
                        else:
                            logger.error("Failed to reset model for production")
                            return False
                    else:
                        logger.info("Model is compatible in production environment")
                        return True
                        
                except Exception as e:
                    logger.warning(f"Could not load model in production: {str(e)}")
                    logger.info("Model will be retrained automatically")
                    return True
            else:
                logger.info("Running in development environment")
                return True
                
        except Exception as e:
            logger.error(f"Error handling production compatibility: {str(e)}")
            return False
'''
    
    # Insert the methods
    new_content = content[:insert_position] + production_methods + content[insert_position:]
    
    # Write the updated content
    with open('services/market_regime_classifier.py', 'w') as f:
        f.write(new_content)
    
    print("✓ Production compatibility methods added successfully")
    return True

if __name__ == "__main__":
    print("Adding production compatibility methods to market_regime_classifier.py...")
    
    if add_production_methods():
        print("✓ All production methods added successfully!")
        print("\nThe market regime classifier now has production compatibility handling.")
    else:
        print("❌ Failed to add production methods")
