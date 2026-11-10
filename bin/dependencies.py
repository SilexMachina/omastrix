"""Read-only Arch prerequisite discovery and approved worker-only installation.

Only the root-owned Omarchy dispatcher crosses the Polkit boundary. This module
and all build/venv code continue to run as the desktop user.
"""
import subprocess

ENGINE_PACKAGES = (
    'base-devel', 'git', 'cmake', 'ninja', 'vulkan-headers', 'vulkan-tools',
    'spirv-headers', 'shaderc',
)


def missing(target, *, strix=False):
    if target == 'engine':
        packages = ENGINE_PACKAGES + (('vulkan-radeon',) if strix else ())
    elif target == 'webui':
        packages = ('uv',)
    else:
        raise ValueError('Unknown dependencies target')
    result = []
    for package in packages:
        check = subprocess.run(['pacman', '-Q', '--', package], capture_output=True,
                               text=True, timeout=15, check=False)
        if check.returncode == 1:
            result.append(package)
        elif check.returncode != 0:
            raise ValueError('Could not check Arch dependencies: ' + package)
    return result


def approval(packages):
    return {'success': False, 'needs_confirm': True, 'confirmation': 'dependencies',
            'packages': list(packages),
            'error': 'Install required Arch packages via Omarchy: ' + ', '.join(packages)
                     + '? Administrator approval will be requested, then installation will continue automatically.'}


def install(target, *, strix=False):
    # Recompute the fixed allowlist here, never trust package names in a request
    # or writable job state. Called only by a detached, explicitly approved job.
    packages = missing(target, strix=strix)
    if not packages:
        return
    result = subprocess.run(['pkexec', '/usr/bin/omarchy', 'pkg', 'add', *packages],
                            check=False)
    if result.returncode:
        raise ValueError('Installing dependencies was denied or failed (exit %s).' % result.returncode)
    remaining = missing(target, strix=strix)
    if remaining:
        raise ValueError('Installing dependencies did not register packages: ' + ', '.join(remaining))
