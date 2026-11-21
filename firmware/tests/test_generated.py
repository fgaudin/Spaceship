"""The committed generated/ files match protocol/panels/*.json: a panel changed without `python tools/gen_module.py
--all` fails here (the wiring tables and headers would describe the old panel)."""
import filecmp, os, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import gen_module  # noqa: E402


def test_generated_files_are_up_to_date():
    committed = os.path.join(HERE, 'generated')
    with tempfile.TemporaryDirectory() as fresh:
        gen_module.OUT = fresh
        for name in sorted(os.listdir(gen_module.PANELS)):
            if name.endswith('.json') and name not in ('console.json', 'hardware.json'):
                gen_module.generate(name[:-5])
        stale = []
        for module in sorted(set(os.listdir(fresh)) | set(os.listdir(committed))):
            for file in ('module_config.h', 'WIRING.md'):
                a, b = os.path.join(fresh, module, file), os.path.join(committed, module, file)
                if not (os.path.exists(a) and os.path.exists(b) and filecmp.cmp(a, b, shallow=False)):
                    stale.append(f'{module}/{file}')
        assert not stale, f'run python firmware/tools/gen_module.py --all: stale {stale}'
