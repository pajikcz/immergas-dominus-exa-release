"""Load the stdlib-only client without importing Home Assistant."""
import importlib.util
from pathlib import Path
import sys

name = "dominus_client_under_test"
if name not in sys.modules:
    path = Path(__file__).parents[1] / "custom_components/immergas_dominus_exa/client.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
client = sys.modules[name]
