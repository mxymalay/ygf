import sys

def apply_auto_start_settings(enabled: bool, delay_seconds: int):
    """根据配置更新或移除 Windows 注册表中的开机自启项"""
    if not getattr(sys, 'frozen', False):
        return  # 仅在打包后的 EXE 环境中生效

    try:
        import winreg
        exe_path = sys.executable
        target_cmd = f'"{exe_path}" --delayed-start {delay_seconds}'
        
        # 决定是否写入或删除
        if enabled:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, 
                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                0, 
                winreg.KEY_SET_VALUE | winreg.KEY_READ
            )
            # 检查是否已一致
            try:
                val, _ = winreg.QueryValueEx(key, "YGF_POS_System")
                if val == target_cmd:
                    winreg.CloseKey(key)
                    return
            except WindowsError:
                pass
                
            winreg.SetValueEx(key, "YGF_POS_System", 0, winreg.REG_SZ, target_cmd)
            winreg.CloseKey(key)
            print(f"[*] 成功设置开机自启, 延迟: {delay_seconds} 秒")
        else:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, 
                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                0, 
                winreg.KEY_SET_VALUE | winreg.KEY_READ
            )
            try:
                winreg.DeleteValue(key, "YGF_POS_System")
                print("[*] 成功移除开机自启")
            except FileNotFoundError:
                pass # 已经不存在
            except WindowsError:
                pass
            winreg.CloseKey(key)
            
    except Exception as e:
        print("[!] 开机启动设置失败:", e)
