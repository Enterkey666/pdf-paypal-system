#!/usr/bin/env python3
import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from payment_utils import get_default_payment_provider, get_available_payment_providers
from config_manager import ConfigManager

def main():
    """Test the payment provider selection logic."""
    logger.info("Testing payment provider selection logic...")
    
    # Get the default payment provider
    default_provider = get_default_payment_provider()
    logger.info(f"Default payment provider: {default_provider}")
    
    # Get available payment providers
    available_providers = get_available_payment_providers()
    logger.info(f"Available payment providers: {available_providers}")
    
    # Check if Stripe is available
    if 'stripe' in available_providers:
        logger.info("Stripe is available as a payment provider.")
    else:
        logger.info("Stripe is NOT available as a payment provider.")
    
    # Check config directly
    config = ConfigManager().get_config()
    logger.info(f"Config default_payment_provider: {config.get('default_payment_provider')}")
    logger.info(f"Config enabled_payment_providers: {config.get('enabled_payment_providers')}")
    
    # Test create_payment_link function
    from payment_utils import create_payment_link
    test_result = create_payment_link(
        provider=default_provider,
        customer_name="Test Customer",
        amount=1000
    )
    logger.info(f"Payment link creation result: {test_result}")
    logger.info(f"Generated payment URL: {test_result.get('payment_link')}")
    logger.info(f"Provider used: {test_result.get('provider')}")

if __name__ == "__main__":
    main()
