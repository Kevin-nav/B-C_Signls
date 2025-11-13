#!/usr/bin/env python3
"""
This script discovers and runs all unit tests in the 'tests/' directory.
"""
import unittest
import os

def run_tests():
    """
    Discovers and runs all tests in the 'tests' directory.
    """
    # Get the path to the directory containing this script
    start_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(start_dir, 'tests')

    print(f"Discovering tests in: {test_dir}")

    # Use the default TestLoader to discover tests
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=test_dir, pattern='test_*.py')

    # Use TextTestRunner to run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with a non-zero status code if any tests failed
    if not result.wasSuccessful():
        exit(1)

if __name__ == '__main__':
    print("--- Running Unit Tests ---")
    run_tests()
    print("\n--- Unit Tests Finished ---")
