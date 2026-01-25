#!/usr/bin/env python3
"""
Fast test runner script for the Kalshi trading system.

This script runs optimized tests with live output and minimal API calls.
Use this whenever making significant changes to ensure nothing is broken.
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime


def run_command_live(command, description):
    """Run a command with live output (no buffering)."""
    print(f"\n🔄 {description}...")
    print("-" * 50)
    
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Print output in real-time
        for line in iter(process.stdout.readline, ''):
            print(line, end='')
        
        process.stdout.close()
        return_code = process.wait()
        
        if return_code == 0:
            print(f"\n✅ {description} - SUCCESS")
            return True
        else:
            print(f"\n❌ {description} - FAILED (exit code: {return_code})")
            return False
            
    except KeyboardInterrupt:
        print(f"\n⏹️ {description} - CANCELLED by user")
        try:
            process.terminate()
        except OSError:
            pass
        return False
    except Exception as e:
        print(f"\n❌ {description} - ERROR: {e}")
        return False


def run_quick_tests():
    """Run only quick tests that don't require extensive API calls."""
    print("🚀 QUICK TESTS - Basic functionality only")
    print("=" * 60)
    
    results = []
    
    # Test 1: Import checks (very fast)
    results.append(run_command_live(
        "python -c \"from src.jobs.decide import make_decision_for_market; from src.jobs.execute import execute_position; from src.jobs.track import run_tracking; print('✅ All imports successful')\"",
        "Critical imports check"
    ))
    
    # Test 2: Configuration check (very fast)  
    results.append(run_command_live(
        "python -c \"from src.config.settings import settings; print(f'✅ Primary model: {settings.trading.primary_model}'); print(f'✅ Max position size: {settings.trading.max_position_size_pct}%')\"",
        "Configuration validation"
    ))
    
    # Test 3: Database module (fast)
    results.append(run_command_live(
        "python -c \"from src.utils.database import DatabaseManager; print('✅ Database module working')\"",
        "Database module check"
    ))
    
    return results


def run_full_tests():
    """Run full test suite including API tests."""
    print("🧪 FULL TESTS - Including API calls (may take 2-3 minutes)")
    print("=" * 60)
    
    results = run_quick_tests()
    
    # Test 4: Run optimized pytest (with limited API calls)
    results.append(run_command_live(
        "python -m pytest tests/test_database.py tests/test_helpers.py -v --tb=short -s",
        "Database and helper tests"
    ))
    
    # Test 5: Run decision test (limited to 1 market)
    results.append(run_command_live(
        "python -m pytest tests/test_decide.py::test_make_decision_for_market_creates_position -v --tb=short -s",
        "Decision engine test (1 market)"
    ))
    
    return results


def main():
    """Run tests based on user choice or command line arguments."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Kalshi Trading System Test Suite")
    parser.add_argument("--mode", "-m", choices=["quick", "full", "custom"], 
                        help="Test mode: quick (default), full, or custom")
    parser.add_argument("--pattern", "-p", help="Test pattern for custom mode (e.g., tests/test_decide.py)")
    parser.add_argument("--ci", action="store_true", help="Run in CI mode (non-interactive)")
    
    args = parser.parse_args()
    
    print("🧪 Kalshi Trading System - Test Suite")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Determine test mode
    choice = None
    if args.mode:
        if args.mode == "quick":
            choice = "1"
        elif args.mode == "full":
            choice = "2"
        elif args.mode == "custom":
            choice = "3"
    elif args.ci:
        # CI mode - default to quick tests
        print("🤖 Running in CI mode - defaulting to quick tests")
        choice = "1"
    else:
        # Interactive mode
        print("Choose test mode:")
        print("1. 🚀 Quick tests (30 seconds - imports, config, database)")
        print("2. 🧪 Full tests (2-3 minutes - includes API calls)")
        print("3. 🔧 Custom test (specify which tests to run)")
        print()
        
        try:
            choice = input("Enter choice (1/2/3) or press Enter for quick tests: ").strip()
        except (KeyboardInterrupt, EOFError):
            if sys.stdin.isatty():
                print("\n👋 Cancelled by user")
            else:
                print("\n🤖 Non-interactive environment detected - defaulting to quick tests")
                choice = "1"
    
    # Default to quick tests if no choice made
    if not choice:
        choice = "1"
    
    if choice == "2":
        results = run_full_tests()
    elif choice == "3":
        test_pattern = args.pattern
        if not test_pattern and sys.stdin.isatty():
            try:
                test_pattern = input("Enter test pattern (e.g., tests/test_decide.py): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Cancelled by user")
                return 0
        
        if test_pattern:
            results = run_quick_tests()
            results.append(run_command_live(
                f"python -m pytest {test_pattern} -v --tb=short -s",
                f"Custom test: {test_pattern}"
            ))
        else:
            print("⚠️ No test pattern provided - running quick tests instead")
            results = run_quick_tests()
    else:
        # Default to quick tests
        results = run_quick_tests()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED! ({passed}/{total})")
        print("✅ System is ready for use")
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total} passed)")
        print("🔧 Please fix failing tests before proceeding")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Test runner cancelled by user")
        sys.exit(1) 