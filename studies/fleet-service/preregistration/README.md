# 外部检验预登记文件

正文 `PREREG_M11_EXTERNAL.md` 规定研究对象、服务和结局。执行顺序见 `EXECUTION_PLAN.md`，算法细节见 `APPENDIX_EXECUTION_RULES.md`。版本说明 `REFREEZE_NOTE.md` 定位了开封前的三处修改。清单 `prereg_manifest_v4.txt` 绑定定稿、执行提交和离线彩排记录。对应的 `.ots` 是已升级的 OpenTimestamps 证明。`GATE_OUTPUT.txt` 保存当时的区块核对输出。

从仓库根目录运行以下测试，可将三份定稿、版本说明和清单按原始字节核对。清单中其余彩排与过程文件保存在离线归档。区块证明可使用 OpenTimestamps 客户端配合已同步的比特币节点独立验证。在本目录运行 `ots verify prereg_manifest_v4.txt.ots`，保持同名清单与证明相邻。核对高度 977496 及区块时间 2026-11-25 09:54:39 UTC。授权发生于同日 10:34:39 UTC。

```sh
python -B -m pytest -q -p no:cacheprovider tests/test_external_preregistration.py
```

正文第 36 行修订澄清归属，第 41 行登记与前版同树的执行代码提交，第 118 行写明限时请求的区间可以随墙钟变化，正式运行只取第一次封存的证书。三处修订均先于外部开封。在 1–5 号车上彩排时，执行程序将共享源的每行解析进内存，然后按车号过滤。外部车辆的记录没有被输出、保存或人工查看。版本说明中“早于任何外部队列记录的读取”按这一流程边界理解。

两份澄清分别说明了内存过滤和书面记录失误的处理。一次记录写入已补全，原提交保留。一个彩排请求因墙钟耗时产生了已预列的证书区间差异。正式运行中，次要队列在完整车日门槛停止，阶段二的空证据目录使封存提交失败。先登记已见文件并核对散列，再以空占位完成封存，该阶段只执行了一次。两个主终点已在此之前封存。

# External test preregistration

`PREREG_M11_EXTERNAL.md` defines the population, service and outcomes. `EXECUTION_PLAN.md` specifies the sequence and `APPENDIX_EXECUTION_RULES.md` gives the algorithms. `REFREEZE_NOTE.md` locates the three pre-opening changes. The manifest `prereg_manifest_v4.txt` binds the final documents, execution revision and offline rehearsal records. Its upgraded OpenTimestamps proof is the adjacent `.ots` file. `GATE_OUTPUT.txt` records the contemporary block check.

Run the test above from the repository root to verify the three final documents, the revision note and the manifest as byte strings. The remaining rehearsal and process records in the manifest are held offline. To check the block independently, use an OpenTimestamps client with a synchronised Bitcoin node. In this directory run `ots verify prereg_manifest_v4.txt.ots` with the original manifest next to the proof. Check height 977496 and block time 2026-11-25 09:54:39 UTC. Opening was authorised that day at 10:34:39 UTC.

Line 36 revised the attribution of a clarification. Line 41 identified the execution revision with the same tree as the previous version. Line 118 documented variability at the wall-clock limit and made the first sealed formal certificate binding. All three changes preceded external opening. During rehearsal on ranks 1–5, each shared-source row was parsed in memory and filtered by vehicle identifier. External records were never output, saved or inspected by a person. The revision note’s statement about reading external records refers to this procedural boundary.

Two clarifications addressed in-memory filtering and errors in the written record. An incomplete entry was filled in with its original commit retained. One rehearsal request exhibited a prespecified wall-clock difference in its certificate interval. During formal execution the secondary cohort stopped at the complete-duty threshold. Its empty evidence directory prevented the second stage from being committed. The files already seen were recorded and hashed, and the original stage was sealed with an empty placeholder. The stage ran once. Both primary endpoints had already been sealed.
