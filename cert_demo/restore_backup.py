"""Verify a backup and restore into a NEW directory; never overwrite live data."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile


def restore_backup(archive, target):
    target = Path(target).resolve()
    if target.exists():
        raise ValueError('目标目录已存在，请指定全新的目录，避免覆盖现有数据')
    if not target.parent.is_dir():
        raise ValueError('目标目录的父目录须已存在')
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or 'manifest.json' not in names:
            raise ValueError('备份目录重复或缺少清单')
        if any(i.file_size > 512 * 1024**2 for i in z.infolist()) or sum(i.file_size for i in z.infolist()) > 4 * 1024**3:
            raise ValueError('备份超过离线恢复工具的大小限制')
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('format') != 1 or set(names) != set(manifest['files']) | {'manifest.json'} or 'demo.sqlite3' not in names:
            raise ValueError('备份清单不完整或版本不支持')
        for name in manifest['files']:
            p = PurePosixPath(name)
            if '\\' in name or ':' in name or str(p) != name or p.is_absolute() or '..' in p.parts or any(part.endswith(('.', ' ')) for part in p.parts) or not (name == 'demo.sqlite3' or name.startswith('images/')):
                raise ValueError('备份包含非法路径')
            if hashlib.sha256(z.read(name)).hexdigest() != manifest['files'][name]:
                raise ValueError('备份文件校验失败：' + name)
        with tempfile.TemporaryDirectory(prefix='cert-restore-', dir=target.parent) as temp:
            staging = Path(temp) / 'data'
            staging.mkdir()
            for name in manifest['files']:
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
            with closing(sqlite3.connect(staging / 'demo.sqlite3')) as c, c:
                if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('数据库完整性检查未通过')
                for rid, payload in c.execute('SELECT id,payload FROM records').fetchall():
                    r = json.loads(payload)
                    for key in ['image_path', 'display_path']:
                        if r.get(key):
                            rel = manifest['image_paths'].get(r[key])
                            if not rel or rel not in manifest['files'] or not rel.startswith('images/'):
                                raise ValueError('证书图片引用不完整')
                            r[key] = str(target / rel)
                    if r['job_status'] in ['running', 'queued']:
                        r.update(job_status='error', error='从备份恢复，请重新识别', version=r['version'] + 1)
                    c.execute('UPDATE records SET payload=? WHERE id=?', (json.dumps(r, ensure_ascii=False), rid))
            # Only publish a fully verified restore. Target must still not exist.
            if target.exists():
                raise ValueError('目标目录已被占用')
            staging.rename(target)
    return target


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--target', required=True, type=Path)
    args = p.parse_args()
    print('已校验并恢复到：', restore_backup(args.archive, args.target))
    print('原数据未覆盖。停止服务后，将 CERT_DEMO_DATA 设置为此目录并重新启动。')
