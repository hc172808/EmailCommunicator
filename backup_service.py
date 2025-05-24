"""
Backup service for email server
Handles database backups, file backups, and external drive management
"""

import os
import json
import shutil
import subprocess
import tempfile
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from flask import current_app
from app import db
import psutil

class BackupService:
    """Service for handling backup operations"""
    
    def __init__(self):
        self.backup_base_path = "/tmp/email_backups"
        self.external_drives = []
        self.backup_config = {
            'auto_backup_enabled': False,
            'backup_frequency': 'daily',  # daily, weekly, monthly
            'retention_days': 30,
            'backup_database': True,
            'backup_files': True,
            'backup_configs': True,
            'compression_enabled': True,
            'external_drive_path': None
        }
        
    def detect_external_drives(self):
        """Detect available external drives and USB devices"""
        drives = []
        
        try:
            # Get all mounted drives
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                # Skip system partitions
                if partition.mountpoint in ['/', '/boot', '/home', '/var', '/tmp']:
                    continue
                    
                # Check if it's a removable drive
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    drive_info = {
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total_gb': round(usage.total / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2),
                        'used_gb': round(usage.used / (1024**3), 2),
                        'is_removable': self._is_removable_drive(partition.device)
                    }
                    drives.append(drive_info)
                except (PermissionError, OSError):
                    continue
                    
        except Exception as e:
            logging.error(f"Error detecting drives: {str(e)}")
            
        return drives
    
    def _is_removable_drive(self, device):
        """Check if a drive is removable (USB, external HDD, etc.)"""
        try:
            # Check if device is in /dev/sd* (SCSI/SATA/USB drives)
            if '/dev/sd' in device or '/dev/hd' in device:
                # Check if it's removable using sys filesystem
                device_name = device.split('/')[-1].rstrip('0123456789')
                removable_path = f"/sys/block/{device_name}/removable"
                
                if os.path.exists(removable_path):
                    with open(removable_path, 'r') as f:
                        return f.read().strip() == '1'
                        
            # Check for USB devices
            if 'usb' in device.lower() or '/media/' in device or '/mnt/' in device:
                return True
                
        except Exception:
            pass
            
        return False
    
    def create_database_backup(self, backup_dir):
        """Create PostgreSQL database backup"""
        try:
            db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
            if not db_url:
                raise Exception("Database URL not configured")
                
            # Parse database URL
            if db_url.startswith('postgresql://'):
                # Extract connection details
                backup_filename = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
                backup_path = os.path.join(backup_dir, backup_filename)
                
                # Create pg_dump command
                cmd = [
                    'pg_dump',
                    db_url,
                    '-f', backup_path,
                    '--no-owner',
                    '--no-privileges',
                    '--clean'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    return backup_path
                else:
                    raise Exception(f"pg_dump failed: {result.stderr}")
                    
            else:
                raise Exception("Only PostgreSQL backups are supported")
                
        except Exception as e:
            logging.error(f"Database backup failed: {str(e)}")
            raise
    
    def create_files_backup(self, backup_dir):
        """Create backup of important files"""
        try:
            files_backup_dir = os.path.join(backup_dir, 'files')
            os.makedirs(files_backup_dir, exist_ok=True)
            
            # List of important directories/files to backup
            important_paths = [
                'static/profile_pics',
                'templates',
                'static',
                '.env',
                'models.py',
                'routes.py',
                'app.py',
                'main.py',
                'security.py',
                'forms.py',
                'email_service.py'
            ]
            
            backed_up_files = []
            
            for path in important_paths:
                if os.path.exists(path):
                    dest_path = os.path.join(files_backup_dir, path)
                    dest_dir = os.path.dirname(dest_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    
                    if os.path.isfile(path):
                        shutil.copy2(path, dest_path)
                        backed_up_files.append(path)
                    elif os.path.isdir(path):
                        if os.path.exists(dest_path):
                            shutil.rmtree(dest_path)
                        shutil.copytree(path, dest_path)
                        backed_up_files.append(path)
            
            return files_backup_dir, backed_up_files
            
        except Exception as e:
            logging.error(f"Files backup failed: {str(e)}")
            raise
    
    def create_config_backup(self, backup_dir):
        """Create backup of configuration data"""
        try:
            config_backup_dir = os.path.join(backup_dir, 'config')
            os.makedirs(config_backup_dir, exist_ok=True)
            
            # Backup environment variables (without sensitive data)
            env_backup = {}
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            # Don't backup sensitive information
                            if 'PASSWORD' in key.upper() or 'SECRET' in key.upper():
                                env_backup[key] = '[HIDDEN]'
                            else:
                                env_backup[key] = value
            
            # Save configuration
            config_file = os.path.join(config_backup_dir, 'environment.json')
            with open(config_file, 'w') as f:
                json.dump(env_backup, f, indent=2)
            
            # Backup system info
            system_info = {
                'backup_date': datetime.now().isoformat(),
                'python_version': subprocess.run(['python3', '--version'], 
                                               capture_output=True, text=True).stdout.strip(),
                'pip_packages': subprocess.run(['pip', 'freeze'], 
                                             capture_output=True, text=True).stdout.strip().split('\n')
            }
            
            system_file = os.path.join(config_backup_dir, 'system_info.json')
            with open(system_file, 'w') as f:
                json.dump(system_info, f, indent=2)
            
            return config_backup_dir
            
        except Exception as e:
            logging.error(f"Config backup failed: {str(e)}")
            raise
    
    def create_full_backup(self, external_drive_path=None):
        """Create a complete backup of the email server"""
        try:
            # Create backup directory
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"emailserver_backup_{timestamp}"
            
            if external_drive_path and os.path.exists(external_drive_path):
                backup_dir = os.path.join(external_drive_path, 'emailserver_backups', backup_name)
            else:
                backup_dir = os.path.join(self.backup_base_path, backup_name)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            backup_info = {
                'backup_date': datetime.now().isoformat(),
                'backup_type': 'full',
                'backup_location': backup_dir
            }
            
            # Create database backup
            if self.backup_config['backup_database']:
                try:
                    db_backup_path = self.create_database_backup(backup_dir)
                    backup_info['database_backup'] = os.path.basename(db_backup_path)
                    backup_info['database_size'] = os.path.getsize(db_backup_path)
                except Exception as e:
                    backup_info['database_error'] = str(e)
            
            # Create files backup
            if self.backup_config['backup_files']:
                try:
                    files_dir, backed_up_files = self.create_files_backup(backup_dir)
                    backup_info['files_backup'] = 'files/'
                    backup_info['backed_up_files'] = backed_up_files
                except Exception as e:
                    backup_info['files_error'] = str(e)
            
            # Create config backup
            if self.backup_config['backup_configs']:
                try:
                    config_dir = self.create_config_backup(backup_dir)
                    backup_info['config_backup'] = 'config/'
                except Exception as e:
                    backup_info['config_error'] = str(e)
            
            # Save backup info
            info_file = os.path.join(backup_dir, 'backup_info.json')
            with open(info_file, 'w') as f:
                json.dump(backup_info, f, indent=2)
            
            # Compress backup if enabled
            if self.backup_config['compression_enabled']:
                zip_path = f"{backup_dir}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(backup_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, backup_dir)
                            zipf.write(file_path, arc_name)
                
                # Remove uncompressed directory
                shutil.rmtree(backup_dir)
                backup_info['compressed'] = True
                backup_info['backup_file'] = zip_path
                backup_info['backup_size'] = os.path.getsize(zip_path)
            else:
                backup_info['compressed'] = False
                backup_info['backup_size'] = self._get_directory_size(backup_dir)
            
            return backup_info
            
        except Exception as e:
            logging.error(f"Full backup failed: {str(e)}")
            raise
    
    def _get_directory_size(self, directory):
        """Calculate total size of directory"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size
    
    def list_backups(self, external_drive_path=None):
        """List available backups"""
        backups = []
        
        # Check local backups
        if os.path.exists(self.backup_base_path):
            for item in os.listdir(self.backup_base_path):
                item_path = os.path.join(self.backup_base_path, item)
                backup_info = self._get_backup_info(item_path)
                if backup_info:
                    backup_info['location'] = 'local'
                    backups.append(backup_info)
        
        # Check external drive backups
        if external_drive_path and os.path.exists(external_drive_path):
            backup_path = os.path.join(external_drive_path, 'emailserver_backups')
            if os.path.exists(backup_path):
                for item in os.listdir(backup_path):
                    item_path = os.path.join(backup_path, item)
                    backup_info = self._get_backup_info(item_path)
                    if backup_info:
                        backup_info['location'] = 'external'
                        backups.append(backup_info)
        
        # Sort by date (newest first)
        backups.sort(key=lambda x: x.get('backup_date', ''), reverse=True)
        return backups
    
    def _get_backup_info(self, backup_path):
        """Get information about a backup"""
        try:
            if backup_path.endswith('.zip'):
                # Compressed backup
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    if 'backup_info.json' in zipf.namelist():
                        with zipf.open('backup_info.json') as f:
                            info = json.load(f)
                            info['backup_file'] = backup_path
                            info['backup_size'] = os.path.getsize(backup_path)
                            return info
            else:
                # Directory backup
                info_file = os.path.join(backup_path, 'backup_info.json')
                if os.path.exists(info_file):
                    with open(info_file, 'r') as f:
                        info = json.load(f)
                        info['backup_file'] = backup_path
                        info['backup_size'] = self._get_directory_size(backup_path)
                        return info
        except Exception as e:
            logging.error(f"Error reading backup info: {str(e)}")
        
        return None
    
    def delete_backup(self, backup_path):
        """Delete a backup"""
        try:
            if os.path.exists(backup_path):
                if os.path.isfile(backup_path):
                    os.remove(backup_path)
                else:
                    shutil.rmtree(backup_path)
                return True
        except Exception as e:
            logging.error(f"Error deleting backup: {str(e)}")
        return False
    
    def cleanup_old_backups(self, external_drive_path=None):
        """Clean up old backups based on retention policy"""
        retention_date = datetime.now() - timedelta(days=self.backup_config['retention_days'])
        cleaned_count = 0
        
        backups = self.list_backups(external_drive_path)
        
        for backup in backups:
            try:
                backup_date = datetime.fromisoformat(backup['backup_date'].replace('Z', '+00:00'))
                if backup_date < retention_date:
                    if self.delete_backup(backup['backup_file']):
                        cleaned_count += 1
            except Exception as e:
                logging.error(f"Error processing backup for cleanup: {str(e)}")
        
        return cleaned_count
    
    def get_backup_config(self):
        """Get current backup configuration"""
        return self.backup_config.copy()
    
    def update_backup_config(self, config):
        """Update backup configuration"""
        self.backup_config.update(config)
        # Save to file
        config_file = 'backup_config.json'
        with open(config_file, 'w') as f:
            json.dump(self.backup_config, f, indent=2)
    
    def load_backup_config(self):
        """Load backup configuration from file"""
        config_file = 'backup_config.json'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    saved_config = json.load(f)
                    self.backup_config.update(saved_config)
            except Exception as e:
                logging.error(f"Error loading backup config: {str(e)}")

# Global backup service instance
backup_service = BackupService()
backup_service.load_backup_config()