# The install scripts cannot run here (no PowerShell), so this checks that what they hard-code matches the Python
# side: task name, file names, firewall group, data folder, helper entry point. Run: python3 test_install_scripts.py
import os
import re

import eden_winclient as client
import eden_winfw as fw
import eden_winhelper as hp

HERE = os.path.dirname(os.path.abspath(__file__))
read = lambda *p: open(os.path.join(HERE, *p), encoding="utf-8").read()
system, user, uninstall = read("install", "install-system.ps1"), read("install", "install-user.ps1"), read("install", "uninstall.ps1")


def test_names_match():
    assert f"'{client.TASK_NAME}'" in system and f"'{client.TASK_NAME}'" in uninstall
    assert f"-Group '{fw.GROUP}'" in uninstall
    for f in ("eden_winhelper.py", "eden_winfw.py"):
        assert f in system and os.path.exists(os.path.join(HERE, f))
    assert "helper.key" in system and "allowed_ports" in system
    assert "Join-Path $env:ProgramData 'Eden'" in system and "Join-Path $env:ProgramData 'Eden'" in uninstall
    assert hp.data_dir({}).replace("\\", "/").endswith("ProgramData/Eden")
    assert "serve" in system and 'serve' in open(os.path.join(HERE, "eden_winhelper.py")).read()


def test_requirements_cover_third_party_imports():
    wanted = {"fastapi", "uvicorn", "pydantic", "psutil", "pyotp", "qrcode"}
    names = {re.split(r"[\[<>=]", l.strip())[0] for l in read("requirements-windows.txt").splitlines() if l.strip() and not l.startswith("#")}
    assert wanted <= names, wanted - names


def test_scripts_are_careful():
    assert "-RunLevel Highest" in system and "-ExecutionTimeLimit" in system
    assert "AtLogOn" not in system and "AtStartup" not in system, "the helper must never start at boot"
    assert "/inheritance:r" in system
    assert "WindowsApps" in system and "USERPROFILE" in system, "the Python used by the elevated helper must not be user-writable"
    assert "IsInRole" in user and "Fail" in user
    for text in (system, user, uninstall):
        assert text.count("{") == text.count("}") and text.count("(") == text.count(")"), "unbalanced brackets"
        assert "C:\\Users" not in text, "no absolute user paths"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("INSTALL SCRIPT CHECKS PASSED")
