# 服务器部署记录

- 主机：192.168.3.117（Proxmox VM 111）
- SSH 用户：learned；密码不写入部署文件。
- 实际系统：Ubuntu 24.04.2，8 vCPU、8 GiB 内存、60 GiB 磁盘。
- 应用目录：`/home/learned/invoice-system`
- 网页：`http://192.168.3.117/invoices`
- 服务：`invoice-system.service`，已设置开机自启。
- 模型：PP-OCRv5_server_det、PP-OCRv5_server_rec、两个方向分类模型；复用本地验证过的权重。
- 运行库：CPU PaddlePaddle 3.2.2、PaddleOCR 3.3.2、PaddleX 3.3.12。

已有发票数据库通过 SQLite backup 迁移，包含 38 条记录（含回收站）、账号和图片。保留账号密码哈希，清除迁移副本的登录会话，重新登录即可。Windows 图片路径已转换为服务器路径。本地原始数据未修改。

## 运维命令

```bash
ssh learned@192.168.3.117
sudo systemctl status invoice-system --no-pager
sudo journalctl -u invoice-system -n 100 --no-pager
sudo systemctl restart invoice-system
```

Nginx 只转发发票页面、静态文件及带鉴权的发票 API；应用本身监听 127.0.0.1:8765。当前为局域网 HTTP 部署。如需公网访问，应配置域名、HTTPS 和注册策略后再开放。

## 初次硬件检查

初始 QEMU 虚拟 CPU 缺少 AVX；需要在 Proxmox 完全关机后把处理器类型改为 host，再开机。程序会在加载 OCR 前检查 AVX，避免不兼容的本地运行库导致网页服务崩溃。硬件调整后仍需实际 OCR 验证，不能仅凭安装成功判定识别服务可用。

## 已完成验证

2026-09-22：host 设置生效，服务器识别为 Intel Xeon E5-2680 v4，AVX/AVX2 可用。服务器 52 项回归测试全部通过，pip check 无冲突。开机后应用和 nginx 均为 active，应用为 enabled。SQLite integrity_check 为 ok，检查时 42 条记录的原始图片均存在。

真实 OCR 测试只读取已有图片，不改动业务记录。四个模型首次加载 15.748 秒；每类一张，重复两次：

| 样本 | 第一次 OCR | 第二次 OCR | 关键结果 |
|---|---:|---:|---|
| 餐费普票 | 8.810 秒 | 6.593 秒 | 563.21 + 33.79 = 597.00，6% |
| 公司往来专票 | 13.143 秒 | 9.013 秒 | 31502.73 + 315.03 = 31817.76，1% |
| 火车票 | 5.572 秒 | 6.318 秒 | 含税 469.00；按业务规则推导 430.28 + 38.72，9% |

六次测试均无必填字段缺失或金额校验错误。这是三个样本的 CPU 推理时间，包含模型内部处理，不含上传、PDF 渲染、队列等待和首次模型加载，不能作为并发性能承诺。脚本为 deploy/check_ocr.py，服务器日志为 /home/learned/invoice-system/ocr-check.log。

HTTP 检查：/invoices 返回 200，未登录发票 API 返回 401，/api/state 返回 404。浏览器自动化在本环境超时，未完成视觉检查；页面网络与接口检查已完成。
