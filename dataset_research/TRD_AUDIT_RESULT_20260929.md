# 美团 TRD 预注册审计结果

- 预注册：`TRD_PREREGISTRATION_20260929.md`（规则未改动）
- 导出：`privedge/privedge/adapters/export_trd.py` → `privedge/data/meituan_trd/`（`domain.json` 含审计计数与 SHA-256；不含用户 ID）

| Gate | 判定 | 关键数字 |
|---|---|---|
| A 许可与来源 | 通过（附待确认事项） | Zenodo 8025855，open，CC BY 4.0；orders_train MD5 与登记值一致。美团授权说明缺失，建议邮件确认上传者 |
| B 结构 | **通过** | 11 个商圈全部 ≥5,000（5,830–38,169）；类别域 122；单类最大占比 0.086–0.113（<0.3） |
| C/D 公开上下文 | 不适用 | 无商圈坐标；v4.1 主线不用上下文 |
| E LDP 可行性 | 已执行 | 见 `privedge/experiments_prereg/UTILITY_V1_RESULT.md`、`SECURITY_V2_RESULT.md` |

事件规则执行计数：订单 1,299,045 行（aor_id 无缺失）；有首单的用户 200,000；首单餐厅品类为"未知"而丢弃 16,653 人，餐厅不在目录中而丢弃 1 人；保留 183,346 人。
