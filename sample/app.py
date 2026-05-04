
import os
import platform

app_env = os.environ.get("APP_ENV", "unknown")
greeting = os.environ.get("GREETING", "Hello")

print("=" * 40)
print("  Docksmith Container Running!")
print("=" * 40)
print(f"  Greeting    : {greeting}")
print(f"  Environment : {app_env}")
print(f"  Working dir : {os.getcwd()}")
print("=" * 40)
# updated
