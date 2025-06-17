from setuptools import setup, find_packages

setup(
    name="pdf-paypal-system",
    version="0.1.0",
    packages=find_packages(),
    py_modules=[
        "customer_extractor",
        "text_normalizer",
        "amount_extractor",
        "ai_ocr",
        "config_manager",
        "enhanced_ocr",
        "extractors",
        "interactive_correction",
        "paypal_utils",
        "template_matching"
    ],
    include_package_data=True,
    install_requires=[
        # Dependencies are already in requirements.txt
    ],
)
