# Server deployment

Target: learned@192.168.3.117, VM 111. Actual OS Ubuntu 24.04, 8 vCPU, 8 GiB RAM.

Use CPU PaddlePaddle 3.2.2, PaddleOCR 3.3.2 and PaddleX 3.3.12 with the four previously verified local model weights. Keep GPU behavior by default on the Windows workstation; set CERT_OCR_DEVICE=cpu for the server. CPU model path remapping handles Windows paths on Linux.

Application listens on loopback 8765, nginx exposes only invoice UI/auth/API on port 80 for the LAN. Existing certificate endpoints remain unreachable through nginx. systemd runs the process as learned and restarts on failure.

Migration uses SQLite backup, copies images, translates stored image paths and clears copied login sessions. Existing account password hashes are preserved. No overwrite of a pre-existing server deployment without a backup. Local data remains unchanged.

Validation: local regression suite, remote CPU instruction check, dependency import, actual OCR of a sample PDF, authenticated endpoint and export checks, anonymous access denial. Current virtual CPU lacks AVX; request Proxmox CPU type host and power cycle before model verification.
