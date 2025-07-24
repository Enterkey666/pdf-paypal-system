#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
バックアップ管理システム
データベース、設定ファイル、アップロードファイルの自動バックアップ
"""

import os
import sys
import subprocess
import shutil
import logging
import tarfile
import json
import schedule
import time
from datetime import datetime, timedelta
from pathlib import Path
import argparse

class BackupManager:
    """バックアップ管理クラス"""
    
    def __init__(self, config_file="backup_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        self._setup_logging()
        
        # バックアップディレクトリの作成
        self.backup_root = Path(self.config.get('backup_directory', './backups'))
        self.backup_root.mkdir(parents=True, exist_ok=True)
        
        # サブディレクトリの作成
        for subdir in ['database', 'files', 'configs', 'logs']:
            (self.backup_root / subdir).mkdir(exist_ok=True)
    
    def _load_config(self):
        """設定ファイルの読み込み"""
        default_config = {
            "backup_directory": "./backups",
            "retention_days": 30,
            "database": {
                "enabled": True,
                "host": "localhost",
                "port": 5432,
                "database": "pdf_paypal_db",
                "username": "pdf_user",
                "password": os.getenv("POSTGRES_PASSWORD", ""),
                "docker_container": "pdf-paypal-postgres"
            },
            "files": {
                "enabled": True,
                "directories": ["uploads", "data"],
                "exclude_patterns": ["*.tmp", "*.log", "__pycache__"]
            },
            "configs": {
                "enabled": True,
                "files": [".env", "config.json", "security_config.py"],
                "exclude_sensitive": True
            },
            "compression": {
                "enabled": True,
                "algorithm": "gzip"
            },
            "notifications": {
                "enabled": False,
                "email": "",
                "slack_webhook": ""
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # デフォルト設定とマージ
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            except Exception as e:
                logging.error(f"設定ファイル読み込みエラー: {e}")
                return default_config
        else:
            # デフォルト設定ファイルを作成
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
    
    def _setup_logging(self):
        """ログ設定"""
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / 'backup.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def backup_database(self):
        """データベースバックアップ"""
        if not self.config['database']['enabled']:
            self.logger.info("データベースバックアップは無効化されています")
            return False
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_root / 'database' / f'db_backup_{timestamp}.sql'
            
            db_config = self.config['database']
            
            # Dockerコンテナを使用している場合
            if db_config.get('docker_container'):
                cmd = [
                    'docker', 'exec', '-t', db_config['docker_container'],
                    'pg_dump', '-U', db_config['username'], db_config['database']
                ]
                
                with open(backup_file, 'w') as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                
                if result.returncode != 0:
                    self.logger.error(f"データベースバックアップエラー: {result.stderr}")
                    return False
            
            # 直接接続の場合
            else:
                cmd = [
                    'pg_dump',
                    '-h', db_config['host'],
                    '-p', str(db_config['port']),
                    '-U', db_config['username'],
                    '-d', db_config['database'],
                    '-f', str(backup_file)
                ]
                
                env = os.environ.copy()
                env['PGPASSWORD'] = db_config['password']
                
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.logger.error(f"データベースバックアップエラー: {result.stderr}")
                    return False
            
            # 圧縮
            if self.config['compression']['enabled']:
                self._compress_file(backup_file)
            
            self.logger.info(f"データベースバックアップ完了: {backup_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"データベースバックアップ例外: {e}")
            return False
    
    def backup_files(self):
        """ファイルバックアップ"""
        if not self.config['files']['enabled']:
            self.logger.info("ファイルバックアップは無効化されています")
            return False
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.backup_root / 'files' / f'files_backup_{timestamp}'
            backup_dir.mkdir(exist_ok=True)
            
            files_config = self.config['files']
            
            for directory in files_config['directories']:
                if os.path.exists(directory):
                    dest_dir = backup_dir / Path(directory).name
                    
                    # ディレクトリのコピー（除外パターンを考慮）
                    shutil.copytree(
                        directory, 
                        dest_dir,
                        ignore=shutil.ignore_patterns(*files_config.get('exclude_patterns', []))
                    )
                    
                    self.logger.info(f"ディレクトリバックアップ完了: {directory} -> {dest_dir}")
            
            # アーカイブ作成
            archive_file = backup_dir.with_suffix('.tar.gz')
            with tarfile.open(archive_file, 'w:gz') as tar:
                tar.add(backup_dir, arcname=backup_dir.name)
            
            # 元のディレクトリを削除
            shutil.rmtree(backup_dir)
            
            self.logger.info(f"ファイルバックアップ完了: {archive_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"ファイルバックアップ例外: {e}")
            return False
    
    def backup_configs(self):
        """設定ファイルバックアップ"""
        if not self.config['configs']['enabled']:
            self.logger.info("設定ファイルバックアップは無効化されています")
            return False
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.backup_root / 'configs' / f'configs_backup_{timestamp}'
            backup_dir.mkdir(exist_ok=True)
            
            configs_config = self.config['configs']
            
            for config_file in configs_config['files']:
                if os.path.exists(config_file):
                    dest_file = backup_dir / Path(config_file).name
                    
                    # 機密情報を除外する場合
                    if configs_config.get('exclude_sensitive', True) and config_file == '.env':
                        self._backup_env_file(config_file, dest_file)
                    else:
                        shutil.copy2(config_file, dest_file)
                    
                    self.logger.info(f"設定ファイルバックアップ: {config_file}")
            
            # アーカイブ作成
            archive_file = backup_dir.with_suffix('.tar.gz')
            with tarfile.open(archive_file, 'w:gz') as tar:
                tar.add(backup_dir, arcname=backup_dir.name)
            
            # 元のディレクトリを削除
            shutil.rmtree(backup_dir)
            
            self.logger.info(f"設定ファイルバックアップ完了: {archive_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"設定ファイルバックアップ例外: {e}")
            return False
    
    def _backup_env_file(self, source_file, dest_file):
        """環境変数ファイルのバックアップ（機密情報をマスク）"""
        sensitive_keys = [
            'SECRET_KEY', 'ENCRYPTION_KEY',
            'STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET',
            'PAYPAL_CLIENT_SECRET', 'POSTGRES_PASSWORD',
            'ADMIN_PASSWORD', 'MAIL_PASSWORD'
        ]
        
        with open(source_file, 'r') as src, open(dest_file, 'w') as dst:
            for line in src:
                # 機密情報をマスク
                masked_line = line
                for key in sensitive_keys:
                    if line.startswith(f'{key}='):
                        masked_line = f'{key}=***MASKED***\n'
                        break
                dst.write(masked_line)
    
    def _compress_file(self, file_path):
        """ファイル圧縮"""
        if self.config['compression']['algorithm'] == 'gzip':
            compressed_file = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in:
                with tarfile.open(compressed_file, 'w:gz') as tar:
                    tarinfo = tarfile.TarInfo(name=file_path.name)
                    tarinfo.size = file_path.stat().st_size
                    tar.addfile(tarinfo, f_in)
            
            # 元のファイルを削除
            os.remove(file_path)
            self.logger.info(f"ファイルを圧縮: {compressed_file}")
    
    def cleanup_old_backups(self):
        """古いバックアップの削除"""
        try:
            retention_days = self.config.get('retention_days', 30)
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            deleted_count = 0
            for backup_type in ['database', 'files', 'configs', 'logs']:
                backup_dir = self.backup_root / backup_type
                
                if backup_dir.exists():
                    for backup_file in backup_dir.iterdir():
                        if backup_file.is_file():
                            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                            if file_mtime < cutoff_date:
                                backup_file.unlink()
                                deleted_count += 1
                                self.logger.info(f"古いバックアップを削除: {backup_file}")
            
            self.logger.info(f"クリーンアップ完了: {deleted_count} ファイル削除")
            return True
            
        except Exception as e:
            self.logger.error(f"クリーンアップエラー: {e}")
            return False
    
    def full_backup(self):
        """完全バックアップ"""
        self.logger.info("完全バックアップ開始")
        start_time = time.time()
        
        results = {
            'database': self.backup_database(),
            'files': self.backup_files(),
            'configs': self.backup_configs(),
            'cleanup': self.cleanup_old_backups()
        }
        
        end_time = time.time()
        duration = end_time - start_time
        
        success_count = sum(results.values())
        total_count = len(results)
        
        if success_count == total_count:
            self.logger.info(f"完全バックアップ成功 ({duration:.2f}秒)")
            self._send_notification("成功", f"完全バックアップが正常に完了しました（実行時間: {duration:.2f}秒）")
        else:
            self.logger.error(f"完全バックアップ一部失敗 ({success_count}/{total_count})")
            self._send_notification("一部失敗", f"バックアップが一部失敗しました ({success_count}/{total_count})")
        
        return results
    
    def _send_notification(self, status, message):
        """通知送信"""
        if not self.config['notifications']['enabled']:
            return
        
        try:
            # メール通知
            email = self.config['notifications'].get('email')
            if email and shutil.which('mail'):
                subprocess.run([
                    'mail', '-s', f'[PDF-PayPal-Stripe] バックアップ{status}', email
                ], input=message, text=True)
            
            # Slack通知
            slack_webhook = self.config['notifications'].get('slack_webhook')
            if slack_webhook:
                import requests
                payload = {
                    'text': f'[PDF-PayPal-Stripe] バックアップ{status}: {message}'
                }
                requests.post(slack_webhook, json=payload)
                
        except Exception as e:
            self.logger.error(f"通知送信エラー: {e}")
    
    def restore_database(self, backup_file):
        """データベース復元"""
        try:
            if not os.path.exists(backup_file):
                self.logger.error(f"バックアップファイルが見つかりません: {backup_file}")
                return False
            
            db_config = self.config['database']
            
            # Dockerコンテナを使用している場合
            if db_config.get('docker_container'):
                cmd = [
                    'docker', 'exec', '-i', db_config['docker_container'],
                    'psql', '-U', db_config['username'], '-d', db_config['database']
                ]
                
                with open(backup_file, 'r') as f:
                    result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.logger.error(f"データベース復元エラー: {result.stderr}")
                    return False
            
            self.logger.info(f"データベース復元完了: {backup_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"データベース復元例外: {e}")
            return False
    
    def list_backups(self):
        """バックアップ一覧表示"""
        backups = {}
        
        for backup_type in ['database', 'files', 'configs']:
            backup_dir = self.backup_root / backup_type
            backups[backup_type] = []
            
            if backup_dir.exists():
                for backup_file in sorted(backup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                    if backup_file.is_file():
                        file_info = {
                            'name': backup_file.name,
                            'path': str(backup_file),
                            'size': backup_file.stat().st_size,
                            'created': datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
                        }
                        backups[backup_type].append(file_info)
        
        return backups


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description='PDF-PayPal-Stripe バックアップ管理システム')
    parser.add_argument('command', choices=['backup', 'cleanup', 'list', 'restore', 'schedule'],
                       help='実行するコマンド')
    parser.add_argument('--config', default='backup_config.json',
                       help='設定ファイルパス')
    parser.add_argument('--file', help='復元するバックアップファイル（restoreコマンド用）')
    
    args = parser.parse_args()
    
    backup_manager = BackupManager(args.config)
    
    if args.command == 'backup':
        backup_manager.full_backup()
    
    elif args.command == 'cleanup':
        backup_manager.cleanup_old_backups()
    
    elif args.command == 'list':
        backups = backup_manager.list_backups()
        for backup_type, files in backups.items():
            print(f"\n{backup_type.upper()} バックアップ:")
            for file_info in files:
                print(f"  {file_info['name']} ({file_info['size']} bytes) - {file_info['created']}")
    
    elif args.command == 'restore':
        if not args.file:
            print("復元するファイルを --file で指定してください")
            return
        backup_manager.restore_database(args.file)
    
    elif args.command == 'schedule':
        # スケジュール実行
        schedule.every().day.at("02:00").do(backup_manager.full_backup)
        schedule.every().week.do(backup_manager.cleanup_old_backups)
        
        print("バックアップスケジューラーを開始しました...")
        print("- 毎日2:00に完全バックアップ")
        print("- 毎週クリーンアップ")
        
        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == '__main__':
    main()