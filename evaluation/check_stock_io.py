"""Exercise native OJ read/write/edit tools without any model or reference answers."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def check(root):
    from importlib.metadata import version
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.sys_operation import LocalWorkConfig, OperationMode, SysOperationCard
    from openjiuwen.core.sys_operation.cwd import set_cwd
    from openjiuwen.harness.tools import ReadFileTool, WriteFileTool, EditFileTool
    Runner.resource_mgr.add_sys_operation(SysOperationCard(id='io-check', mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(sandbox_root=[str(root)], restrict_to_sandbox=True)))
    operation = Runner.resource_mgr.get_sys_operation('io-check')
    set_cwd(str(root))
    target = root/'sample.txt'
    target.write_text('alpha\nbeta\n')
    cases = [
        (ReadFileTool, dict(file_path=str(target))),
        (WriteFileTool, dict(file_path=str(target), content='alpha\ngamma\n')),
        (EditFileTool, dict(file_path=str(target), old_string='gamma', new_string='delta')),
        (ReadFileTool, dict(file_path=str(target))),
    ]
    for cls, inputs in cases:
        try:
            result = await asyncio.wait_for(cls(operation, language='en', agent_id='io-check').invoke(inputs), 5)
            success = result.success
            error = str(getattr(result, 'error', '') or '')
        except Exception as exc:
            success, error = False, f'{type(exc).__name__}: {exc}'
        print('IO_CHECK', json.dumps(dict(tool=cls.__name__, success=success, error=error,
            filelock=version('filelock')), ensure_ascii=False), flush=True)
        if not success:
            return 1
    assert target.read_text() == 'alpha\ndelta\n'
    print('IO_CHECK all native file operations passed', flush=True)
    return 0


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='oj-native-io-') as temporary:
        root = Path(temporary)
        os.chdir(root)
        sys.exit(asyncio.run(check(root)))
