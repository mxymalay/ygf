"""
杨国福 POS 系统 (C:\\YANGGUOFU-POS) 硬件参数提取工具
自动分析官方软件的串口配置、电子秤驱动及打印机配置
"""
import os
import json
import re


def inspect():
    target_dir = r"C:\YANGGUOFU-POS"
    if not os.path.exists(target_dir):
        print("[!] 未找到目录 %s，尝试全盘搜索..." % target_dir)
        for drive in ["C:", "D:", "E:"]:
            path = os.path.join(drive, "YANGGUOFU-POS")
            if os.path.exists(path):
                target_dir = path
                break

    print("=" * 65)
    print("      正在分析官方软件配置: %s" % target_dir)
    print("=" * 65)

    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    if not os.path.exists(target_dir):
        log("[X] 找不到 %s 目录！" % target_dir)
        return

    # 1. 扫描 serial 文件夹
    serial_dir = os.path.join(target_dir, "serial")
    if os.path.exists(serial_dir):
        log("\n📁 【1. 发现 serial 串口支持目录】:")
        for root, dirs, files in os.walk(serial_dir):
            for file in files:
                fp = os.path.join(root, file)
                log("  -> 找到文件: %s (%d 字节)" % (fp, os.path.getsize(fp)))
                if file.endswith(('.json', '.ini', '.txt', '.cfg', '.js', '.bat', '.cmd', '.py')):
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            log("  --- 文件内容 [%s] ---" % file)
                            log(content[:1500])
                            log("  --- 内容结束 ---")
                    except Exception as e:
                        log("  [!] 读取失败: %s" % e)

    # 2. 扫描 acLas 文件夹 (Aclas 电子秤相关)
    aclas_dir = os.path.join(target_dir, "acLas")
    if os.path.exists(aclas_dir):
        log("\n📁 【2. 发现 acLas (顶尖/电子秤) 驱动目录】:")
        for root, dirs, files in os.walk(aclas_dir):
            for file in files:
                fp = os.path.join(root, file)
                log("  -> 找到电子秤驱动文件: %s" % fp)

    # 3. 扫描 resources 资源与配置文件
    resources_dir = os.path.join(target_dir, "resources")
    if os.path.exists(resources_dir):
        log("\n📁 【3. 扫描 resources 配置与应用资源】:")
        for root, dirs, files in os.walk(resources_dir):
            for file in files:
                if file.endswith(('.json', '.ini', '.cfg', '.js', '.yml', '.env')):
                    fp = os.path.join(root, file)
                    log("  -> 配置文件: %s" % fp)
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if any(k in content.lower() for k in ['com', 'port', 'baud', 'scale', 'weight', 'print', 'serial']):
                                log("  --- 匹配到硬件关键字的配置 [%s] ---" % file)
                                log(content[:2000])
                                log("  --- 配置内容结束 ---")
                    except Exception:
                        pass

    # 4. 扫描 AppData 用户本地配置
    user_appdata = os.path.expanduser(r"~\AppData\Roaming")
    log("\n📁 【4. 扫描 AppData 存储的项目设置】:")
    for item in os.listdir(user_appdata):
        if 'yangguofu' in item.lower() or 'ygf' in item.lower() or 'pos' in item.lower():
            target_user_dir = os.path.join(user_appdata, item)
            log("  -> 找到应用本地数据目录: %s" % target_user_dir)
            for root, dirs, files in os.walk(target_user_dir):
                for file in files:
                    if file.endswith(('.json', '.ini', '.log', '.cfg')):
                        fp = os.path.join(root, file)
                        try:
                            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                log("  --- 本地配置文件 [%s] ---" % fp)
                                log(content[:1500])
                                log("  --- 配置结束 ---")
                        except Exception:
                            pass

    # 保存分析输出到文件
    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ygf_pos_analysis.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    log("\n" + "=" * 65)
    log("分析完成！结果已写入: %s" % out_file)
    log("=" * 65)


if __name__ == "__main__":
    inspect()
