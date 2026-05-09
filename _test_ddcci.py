#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DDC/CI 诊断 v2 - 枚举所有显示器 + 定位外接屏 + 测试VCP
"""
import sys
import ctypes
from ctypes import windll, byref, c_ulong, c_uint, c_ubyte, Structure, c_long, POINTER


class PHYSICAL_MONITOR(Structure):
    _fields_ = [("handle", c_ulong), ("description", c_ulong * 128)]


class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]


MONITORPROC = ctypes.WINFUNCTYPE(c_uint, c_ulong, c_ulong, POINTER(RECT), c_ulong)

found_monitors = []


def _enum_callback(hmon, hdc, lprect, lparam):
    rect = lprect.contents if lprect else RECT()
    info = {
        "hmon": int(hmon),
        "rect": (rect.left, rect.top, rect.right, rect.bottom),
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
        "phys_handles": [],
    }
    try:
        num_phys = c_uint()
        ret = windll.user32.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, byref(num_phys))
        if ret and num_phys.value > 0:
            phys_arr = (PHYSICAL_MONITOR * num_phys.value)()
            r2 = windll.user32.GetPhysicalMonitorsFromHMONITOR(hmon, num_phys.value, byref(phys_arr))
            if r2:
                for p in phys_arr:
                    info["phys_handles"].append(int(p.handle))
    except Exception as e:
        info["error"] = str(e)
    found_monitors.append(info)
    return 1


def main():
    print("=" * 60)
    print("  DDC/CI 显示器枚举诊断 v2")
    print("=" * 60)

    user32 = windll.user32
    dxva2 = windll.dxva2

    # Step 1: 枚举全部显示器
    print("\n[1] 枚举所有显示器 ...")
    found_monitors.clear()
    user32.EnumDisplayMonitors(0, None, MONITORPROC(_enum_callback), 0)

    if not found_monitors:
        print("    FAIL: 没有发现任何显示器!")
        return

    print("    发现 %d 个逻辑显示器:" % len(found_monitors))

    # 获取主显示器 HMONITOR
    primary_hmon = user32.MonitorFromPoint(0, 2)  # MONITOR_DEFAULTTOPRIMARY

    for idx, m in enumerate(found_monitors):
        is_primary = "*" if m["hmon"] == primary_hmon else " "
        r = m["rect"]
        print("")
        print("    #%s%d HMON=%s%s" % (is_primary, idx, hex(m["hmon"]), " [主显]" if is_primary == "*" else ""))
        print("        区域: (%d, %d)-(%d, %d)  分辨率:%dx%d" % (r[0], r[1], r[2], r[3], m["width"], m["height"]))
        if m["phys_handles"]:
            ph_str = ", ".join(hex(h) for h in m["phys_handles"])
            print("        物理句柄: %s" % ph_str)
        else:
            print("        物理句柄: (无法获取)")
        if "error" in m:
            print("        错误: %s" % m["error"])

    # Step 2: 对每个物理句柄测试 DDC/CI VCP
    print("\n[2] DDC/CI VCP 测试 ...")
    any_success = False

    for idx, m in enumerate(found_monitors):
        if not m["phys_handles"]:
            print("\n  --- 显示器#%d 无物理句柄，跳过 ---" % idx)
            continue
        for pi, hPhys in enumerate(m["phys_handles"]):
            print("\n  === 显示器#%d PhysHandle=%s ===" % (idx, hex(hPhys)))

            # VCP 0x00 Manufacturer ID
            vct = c_ubyte(); cur = c_uint(); mx = c_uint()
            try:
                ret = dxva2.GetVCPFeatureAndVCPReply(hPhys, 0x00, byref(vct), byref(cur), byref(mx))
                if ret:
                    print("    OK VCP 0x00 (MfgID): 0x%04X" % cur.value)
                    any_success = True
                else:
                    print("    X  VCP 0x00: 无响应")
            except Exception as e:
                print("    X  VCP 0x00: 异常 - %s" % e)

            # VCP 0x10 Brightness
            vct2 = c_ubyte(); cur2 = c_uint(); mx2 = c_uint()
            try:
                ret2 = dxva2.GetVCPFeatureAndVCPReply(hPhys, 0x10, byref(vct2), byref(cur2), byref(mx2))
                if ret2:
                    print("    OK VCP 0x10 (亮度): %d / max=%d" % (cur2.value, mx2.value))
                    any_success = True
                else:
                    print("    X  VCP 0x10 (亮度): 无响应")
            except Exception as e:
                print("    X  VCP 0x10: 异常 - %s" % e)

            # VCP 0x12 Contrast
            vct3 = c_ubyte(); cur3 = c_uint(); mx3 = c_uint()
            try:
                ret3 = dxva2.GetVCPFeatureAndVCPReply(hPhys, 0x12, byref(vct3), byref(cur3), byref(mx3))
                if ret3:
                    print("    OK VCP 0x12 (对比度): %d / max=%d" % (cur3.value, mx3.value))
                    any_success = True
                else:
                    print("    X  VCP 0x12 (对比度): 无响应")
            except Exception as e:
                print("    X  VCP 0x12: 异常 - %s" % e)

    # 总结
    print("\n" + "=" * 60)
    if any_success:
        print("  结论: 至少一个显示器支持 DDC/CI OK")
        print("  下一步: 根据结果更新 server.py 的选择逻辑")
    else:
        print("  结论: 所有显示器均无 DDC/CI 响应 FAIL")
        print("  可能原因:")
        print("    1. 外接显示器未开启 DDC/CI (检查 OSD)")
        print("    2. 驱动/线缆不支持 DDC/CI")
        print("    3. 需要管理员权限运行此脚本")
    print("=" * 60)


if __name__ == "__main__":
    main()
