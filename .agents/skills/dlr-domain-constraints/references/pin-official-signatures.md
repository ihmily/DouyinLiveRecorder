# 官方签名档

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「构建产物、依赖与运行时基线」下的
> 「发布链运行时二进制必须 fail-closed 钉定」。约束变更以 AGENTS.md 为准。

## 官方签名档

- 属第一层内部的第二种满足方式，**不是新增一个面**。
- 该槽没有公布哈希时验签即**唯一判据**。
- 验签调用点**不得**留在「哈希已过」的分支里（否则该档在真实构建路径上永不可达）。
- 回归锁：`tests/test_build_exe.py::test_signature_mode_slot_downloads_and_actually_verifies`。
- macOS 两槽 ffmpeg 走官方签名档（evermeet 不公布哈希，验签即该槽唯一判据）。
