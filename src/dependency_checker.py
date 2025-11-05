# -*- encoding: utf-8 -*-
"""
[DLR][DEPS] Dependency Checker and Auto-Installer
Author: Claude Code
Date: 2025-11-05
Function: Check and auto-install missing dependencies (ffmpeg, httpx, loguru, PyExecJS)
"""

import sys
import subprocess
import importlib
import shutil
from typing import List, Dict, Optional, Tuple
from pathlib import Path

try:
    from .dlr_logger import dlr_logger, log_deps_check_missing, log_deps_auto_install
except ImportError:
    from dlr_logger import dlr_logger, log_deps_check_missing, log_deps_auto_install


class DependencyChecker:
    """
    # [DLR][DEPS] Dependency Checker and Auto-Installer

    Features:
    - CHECK_MISSING: Check for missing dependencies
    - AUTO_INSTALL: Automatically install missing Python packages
    - FFmpeg detection and installation guidance
    - Detailed error messages with installation instructions
    """

    def __init__(self, auto_install: bool = True):
        """
        Initialize Dependency Checker

        Args:
            auto_install: Automatically install missing packages (default: True)
        """
        self.auto_install = auto_install

        # [DLR][DEPS] Required Python packages
        self.required_packages = {
            'httpx': 'httpx>=0.24.0',
            'loguru': 'loguru>=0.7.0',
            'execjs': 'PyExecJS>=1.5.0',  # Package name differs from import name
        }

        # [DLR][DEPS] Optional packages
        self.optional_packages = {
            'aiofiles': 'aiofiles>=23.0.0',
        }

        dlr_logger.info_deps(f"Initialized: auto_install={auto_install}")

    def check_python_version(self) -> Tuple[bool, str]:
        """
        # [DLR][DEPS] Check Python version (requires 3.10+)

        Returns:
            (is_valid, version_string)
        """
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"

        is_valid = version.major >= 3 and version.minor >= 10

        if is_valid:
            dlr_logger.info_deps(f"Python version: {version_str} ✓")
        else:
            dlr_logger.error_deps(f"Python version: {version_str} (requires >=3.10)")

        return is_valid, version_str

    def check_package(self, import_name: str) -> bool:
        """
        # [DLR][DEPS] Check if a Python package is installed

        Args:
            import_name: Package import name (e.g., 'httpx', 'loguru')

        Returns:
            True if installed, False otherwise
        """
        try:
            importlib.import_module(import_name)
            dlr_logger.debug_deps(f"Package '{import_name}' found ✓")
            return True
        except ImportError:
            log_deps_check_missing(import_name)
            dlr_logger.warn_deps(f"Package '{import_name}' not found")
            return False

    def check_ffmpeg(self) -> Tuple[bool, Optional[str]]:
        """
        # [DLR][DEPS] Check if FFmpeg is installed and accessible

        Returns:
            (is_installed, version_string)
        """
        ffmpeg_path = shutil.which('ffmpeg')

        if not ffmpeg_path:
            log_deps_check_missing('ffmpeg')
            dlr_logger.warn_deps("FFmpeg not found in PATH")
            return False, None

        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # Extract version from output
                version_line = result.stdout.split('\n')[0]
                version = version_line.split(' ')[2] if len(version_line.split(' ')) > 2 else 'unknown'

                dlr_logger.info_deps(f"FFmpeg found: {version} at {ffmpeg_path} ✓")
                return True, version
            else:
                dlr_logger.warn_deps("FFmpeg found but failed to run")
                return False, None

        except Exception as e:
            dlr_logger.error_deps(f"Error checking FFmpeg: {e}")
            return False, None

    def install_package(self, package_spec: str, import_name: str = None) -> bool:
        """
        # [DLR][DEPS] AUTO_INSTALL
        Install a Python package using pip

        Args:
            package_spec: Package specification (e.g., 'httpx>=0.24.0')
            import_name: Import name if different from package name

        Returns:
            True if installation successful, False otherwise
        """
        if not import_name:
            import_name = package_spec.split('>=')[0].split('==')[0]

        log_deps_auto_install(package_spec)

        try:
            dlr_logger.info_deps(f"Installing {package_spec}...")

            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', package_spec],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                dlr_logger.info_deps(f"Successfully installed {package_spec} ✓")
                return True
            else:
                dlr_logger.error_deps(f"Failed to install {package_spec}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            dlr_logger.error_deps(f"Installation timeout for {package_spec}")
            return False
        except Exception as e:
            dlr_logger.error_deps(f"Installation error: {e}")
            return False

    def check_all_dependencies(self) -> Dict[str, bool]:
        """
        # [DLR][DEPS] Check all required dependencies

        Returns:
            Dictionary with dependency check results
        """
        results = {}

        dlr_logger.info_deps("Checking all dependencies...")

        # Check Python version
        py_valid, py_version = self.check_python_version()
        results['python'] = py_valid

        # Check FFmpeg
        ffmpeg_found, ffmpeg_version = self.check_ffmpeg()
        results['ffmpeg'] = ffmpeg_found

        # Check required Python packages
        for import_name, package_spec in self.required_packages.items():
            # Handle special cases where import name != package name
            if import_name == 'execjs':
                check_name = 'execjs'
            else:
                check_name = import_name

            is_installed = self.check_package(check_name)
            results[import_name] = is_installed

            # Auto-install if missing and auto_install enabled
            if not is_installed and self.auto_install:
                dlr_logger.info_deps(f"Attempting auto-install: {package_spec}")
                install_success = self.install_package(package_spec, check_name)
                results[import_name] = install_success

        # Check optional packages (no auto-install)
        for import_name, package_spec in self.optional_packages.items():
            is_installed = self.check_package(import_name)
            results[f"{import_name}_optional"] = is_installed

        return results

    def print_installation_instructions(self, missing: List[str]):
        """
        # [DLR][DEPS] Print installation instructions for missing dependencies
        """
        if not missing:
            dlr_logger.info_deps("All dependencies satisfied ✓")
            return

        dlr_logger.error_deps(f"Missing dependencies: {', '.join(missing)}")
        print("\n" + "=" * 60)
        print("[DLR][DEPS] INSTALLATION INSTRUCTIONS")
        print("=" * 60)

        for dep in missing:
            if dep == 'ffmpeg':
                print("\n📦 FFmpeg:")
                print("  Windows: Download from https://ffmpeg.org/download.html")
                print("  Linux (Ubuntu): sudo apt install ffmpeg")
                print("  Linux (CentOS): sudo yum install ffmpeg")
                print("  macOS: brew install ffmpeg")

            elif dep in self.required_packages:
                package_spec = self.required_packages[dep]
                print(f"\n📦 {dep}:")
                print(f"  pip install {package_spec}")

        print("\n" + "=" * 60)

    def generate_requirements_txt(self, output_path: Path = None):
        """
        # [DLR][DEPS] Generate requirements.txt file

        Args:
            output_path: Output file path (default: ./requirements.txt)
        """
        if output_path is None:
            output_path = Path("requirements.txt")

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("# [DLR] DouyinLiveRecorder Dependencies\n")
                f.write("# Auto-generated by dependency_checker.py\n\n")

                f.write("# Required packages\n")
                for package_spec in self.required_packages.values():
                    f.write(f"{package_spec}\n")

                f.write("\n# Optional packages\n")
                for package_spec in self.optional_packages.values():
                    f.write(f"# {package_spec}\n")

            dlr_logger.info_deps(f"Generated requirements.txt at {output_path}")

        except Exception as e:
            dlr_logger.error_deps(f"Failed to generate requirements.txt: {e}")

    def run_full_check(self) -> bool:
        """
        # [DLR][DEPS] Run full dependency check and return status

        Returns:
            True if all required dependencies are satisfied, False otherwise
        """
        dlr_logger.info_deps("=" * 60)
        dlr_logger.info_deps("[DLR][DEPS] Running full dependency check")
        dlr_logger.info_deps("=" * 60)

        results = self.check_all_dependencies()

        # Collect missing required dependencies
        missing = []
        for dep, is_installed in results.items():
            if dep.endswith('_optional'):
                continue  # Skip optional packages

            if not is_installed:
                missing.append(dep)

        if missing:
            self.print_installation_instructions(missing)
            return False
        else:
            dlr_logger.info_deps("=" * 60)
            dlr_logger.info_deps("✓ All required dependencies are satisfied!")
            dlr_logger.info_deps("=" * 60)
            return True


# [DLR][DEPS] Global dependency checker instance
dependency_checker = DependencyChecker(auto_install=True)


if __name__ == "__main__":
    print("=" * 70)
    print("[DLR][DEPS] DouyinLiveRecorder Dependency Checker")
    print("=" * 70)
    print()

    # Run full check
    all_satisfied = dependency_checker.run_full_check()

    print()

    if all_satisfied:
        print("✅ All dependencies are ready! You can run DouyinLiveRecorder now.")
        sys.exit(0)
    else:
        print("❌ Some dependencies are missing. Please install them before running.")
        sys.exit(1)
