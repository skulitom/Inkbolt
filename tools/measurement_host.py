"""Observed Windows architecture and CPU model, independent of optional env vars."""
import ctypes
from ctypes import wintypes
import os
import platform
import struct
import sys


class NativeSystem(ctypes.Structure):
    # Public SYSTEM_INFO ABI, not an implementation of OS introspection.
    # https://learn.microsoft.com/windows/win32/api/sysinfoapi/ns-sysinfoapi-system_info
    _fields_ = [('architecture', wintypes.WORD), ('reserved', wintypes.WORD),
                ('page_size', wintypes.DWORD), ('minimum', ctypes.c_void_p),
                ('maximum', ctypes.c_void_p), ('active_mask', ctypes.c_size_t),
                ('processors_in_group', wintypes.DWORD), ('obsolete_type', wintypes.DWORD),
                ('allocation_granularity', wintypes.DWORD), ('level', wintypes.WORD),
                ('revision', wintypes.WORD)]


def windows_hardware():
    import winreg
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetNativeSystemInfo.argtypes = [ctypes.POINTER(NativeSystem)]
    api.GetNativeSystemInfo.restype = None
    native = NativeSystem()
    api.GetNativeSystemInfo(ctypes.byref(native))
    names = {0: 'x86', 5: 'ARM', 6: 'IA64', 9: 'AMD64', 12: 'ARM64'}
    if native.architecture not in names or not native.processors_in_group:
        raise ValueError('Unknown native processor architecture/count')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                        r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
        values = [winreg.QueryValueEx(key, name)[0].strip()
                  for name in ('ProcessorNameString', 'Identifier', 'VendorIdentifier')]
    if not all(isinstance(v, str) and v for v in values):
        raise ValueError('Incomplete CPU model description')
    return names[native.architecture], ' | '.join(values)


def identity():
    result = dict(system=platform.system(), release=platform.release(), version=platform.version(),
                  machine=None, pointer_bits=struct.calcsize('P')*8, processor=None,
                  logical_cpus=os.cpu_count(), python=sys.version, hardware_available=False,
                  hardware_source='windows_native_system_info_and_cpu_registry_v1')
    if os.name != 'nt':
        result['hardware_error'] = 'Only the Windows measurement backend is verified'
        return result
    try:
        result['machine'], result['processor'] = windows_hardware()
        result['hardware_available'] = True
    except (OSError, ValueError, TypeError, AttributeError) as error:
        result['hardware_error'] = f'{type(error).__name__}: {error}'
    return result
