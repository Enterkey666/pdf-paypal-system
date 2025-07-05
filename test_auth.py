#!/usr/bin/env python3
"""
Authentication system test script
"""

import os
import sys
import logging

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test if all required modules can be imported"""
    try:
        import database
        logger.info("✓ database module imported successfully")
        
        import auth
        logger.info("✓ auth module imported successfully")
        
        # Test database functions
        user_count = database.get_user_count()
        logger.info(f"✓ User count: {user_count}")
        
        # Test user creation
        success, result = database.create_user("testuser", "testpass", email="test@example.com", is_admin=True)
        if success:
            logger.info(f"✓ Test user created with ID: {result}")
        else:
            logger.info(f"ℹ User creation result: {result}")
        
        # Test user lookup
        user = database.get_user_by_username("testuser")
        if user:
            logger.info(f"✓ Test user found: {user.username}, Admin: {user.is_admin}")
        else:
            logger.info("ℹ Test user not found")
        
        return True
    except Exception as e:
        logger.error(f"✗ Import/test failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Testing authentication system...")
    if test_imports():
        logger.info("✓ All tests passed")
    else:
        logger.error("✗ Tests failed")