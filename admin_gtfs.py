"""
Admin routes for GTFS data management and scheduling.
"""

import os
import json
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from gtfs_scheduler import GTFSScheduler
from email_fetcher import EmailFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='admin_gtfs.log'
)

logger = logging.getLogger(__name__)

# Create blueprint
admin_gtfs = Blueprint('admin_gtfs', __name__)

# Initialize scheduler
scheduler = GTFSScheduler()

@admin_gtfs.route('/admin/gtfs', methods=['GET'])
@login_required
def gtfs_manager():
    """
    Render the GTFS manager page.
    """
    if not current_user.is_admin:
        flash('Admin privileges required', 'error')
        return redirect(url_for('index'))
    
    # Get scheduler configuration
    config = {
        'update_time': scheduler.update_time,
        'update_days': scheduler.update_days,
        'email_filter': scheduler.email_filter,
        'update_directory': scheduler.update_directory,
        'enable_historical': scheduler.enable_historical,
        'next_update': scheduler.get_next_update_time(),
        'is_running': scheduler.running
    }
    
    # Get list of recent GTFS updates
    update_files = []
    if os.path.exists(scheduler.update_directory):
        for filename in os.listdir(scheduler.update_directory):
            if filename.endswith('.json'):
                file_path = os.path.join(scheduler.update_directory, filename)
                stats = os.stat(file_path)
                file_size = stats.st_size / (1024 * 1024)  # Convert to MB
                update_time = datetime.fromtimestamp(stats.st_mtime)
                
                update_files.append({
                    'filename': filename,
                    'size': f"{file_size:.2f} MB",
                    'date': update_time.strftime("%Y-%m-%d %H:%M:%S"),
                    'path': file_path
                })
        
        # Sort by date (newest first)
        update_files.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template(
        'admin_gtfs.html', 
        config=config,
        updates=update_files,
        active_page="gtfs",
        title="GTFS Manager"
    )

@admin_gtfs.route('/admin/gtfs/config', methods=['POST'])
@login_required
def update_gtfs_config():
    """
    Update GTFS scheduler configuration.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        data = request.json
        
        # Extract configuration updates
        config_updates = {}
        
        if 'update_time' in data:
            config_updates['update_time'] = data['update_time']
            
        if 'update_days' in data:
            days = data['update_days']
            if isinstance(days, str):
                days = days.lower().split(',')
                days = [day.strip() for day in days]
            config_updates['update_days'] = days
            
        if 'email_subject' in data:
            if 'email_filter' not in config_updates:
                config_updates['email_filter'] = {}
            config_updates['email_filter']['subject'] = data['email_subject']
            
        if 'days_back' in data:
            if 'email_filter' not in config_updates:
                config_updates['email_filter'] = {}
            try:
                days_back = int(data['days_back'])
                config_updates['email_filter']['days_back'] = days_back
            except ValueError:
                pass
            
        if 'sender_filter' in data:
            if 'email_filter' not in config_updates:
                config_updates['email_filter'] = {}
            config_updates['email_filter']['sender'] = data['sender_filter'] or None
            
        if 'enable_historical' in data:
            config_updates['enable_historical'] = data['enable_historical'] == 'true'
        
        # Update scheduler configuration
        success = scheduler.update_config(config_updates)
        
        if success:
            # If scheduler is running, restart it to apply new schedule
            if scheduler.running:
                scheduler.stop()
                scheduler.start()
                
            return jsonify({'success': True, 'message': 'Configuration updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update configuration'})
            
    except Exception as e:
        logger.error(f"Error updating GTFS configuration: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_gtfs.route('/admin/gtfs/email', methods=['POST'])
@login_required
def update_email_config():
    """
    Update email credentials for GTFS updates.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        data = request.json
        
        use_env_vars = data.get('use_env_vars', 'true') == 'true'
        email = data.get('email')
        password = data.get('password')
        
        success = scheduler.configure_email_credentials(
            email=email,
            password=password,
            use_env_vars=use_env_vars
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Email configuration updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update email configuration'})
            
    except Exception as e:
        logger.error(f"Error updating email configuration: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_gtfs.route('/admin/gtfs/test_email', methods=['POST'])
@login_required
def test_email_connection():
    """
    Test connection to the email server.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        # Create a new fetcher for testing
        fetcher = EmailFetcher()
        
        # Check if we should use provided credentials
        data = request.json
        use_provided = data.get('use_provided', False)
        
        if use_provided:
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return jsonify({'success': False, 'error': 'Email and password required'}), 400
                
            fetcher.set_credentials(email, password)
        
        # Test connection
        success = fetcher.connect()
        
        if success:
            fetcher.disconnect()
            return jsonify({'success': True, 'message': 'Successfully connected to email server'})
        else:
            return jsonify({'success': False, 'error': 'Failed to connect to email server'})
            
    except Exception as e:
        logger.error(f"Error testing email connection: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_gtfs.route('/admin/gtfs/scheduler', methods=['POST'])
@login_required
def control_scheduler():
    """
    Start or stop the GTFS scheduler.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        action = request.json.get('action')
        
        if action == 'start':
            success = scheduler.start()
            message = 'Scheduler started successfully'
        elif action == 'stop':
            success = scheduler.stop()
            message = 'Scheduler stopped successfully'
        elif action == 'update_now':
            success = scheduler.run_update_now()
            message = 'Manual update completed successfully' if success else 'Manual update failed'
        else:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
            
        return jsonify({
            'success': success, 
            'message': message,
            'is_running': scheduler.running,
            'next_update': scheduler.get_next_update_time()
        })
            
    except Exception as e:
        logger.error(f"Error controlling scheduler: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_gtfs.route('/admin/gtfs/upload', methods=['POST'])
@login_required
def upload_gtfs_file():
    """
    Handle manual upload of GTFS data file.
    """
    if not current_user.is_admin:
        flash('Admin privileges required', 'error')
        return redirect(url_for('index'))
    
    if 'gtfs_file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.url)
        
    file = request.files['gtfs_file']
    
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)
        
    if file and file.filename.endswith('.json'):
        # Create upload directory if it doesn't exist
        os.makedirs(scheduler.update_directory, exist_ok=True)
        
        # Save file with timestamp prefix
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = secure_filename(f"{timestamp}_{file.filename}")
        file_path = os.path.join(scheduler.update_directory, filename)
        
        file.save(file_path)
        
        # Process the file
        try:
            # Check that it's valid GTFS JSON
            fetcher = EmailFetcher()
            if fetcher.validate_gtfs_json(file_path):
                from data_processor import update_ferry_data
                result = update_ferry_data(file_path=file_path)
                flash(f'File uploaded and processed successfully: {result}', 'success')
            else:
                flash('File uploaded but invalid GTFS format', 'warning')
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            logger.error(f"Error processing uploaded file: {str(e)}")
    else:
        flash('Invalid file type. Only JSON files are accepted', 'error')
    
    return redirect(url_for('admin_gtfs.gtfs_manager'))

@admin_gtfs.route('/admin/gtfs/file/<path:filename>', methods=['GET'])
@login_required
def get_file_info(filename):
    """
    Get information about a specific GTFS file.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        file_path = os.path.join(scheduler.update_directory, secure_filename(filename))
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        # Parse the file to get basic info
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Extract basic stats
        stats = {
            'filename': filename,
            'size': os.path.getsize(file_path) / (1024 * 1024),  # Size in MB
            'routes': len(data.get('routes', [])),
            'vessels': len(set(v.get('vessel') for v in data.get('routes', []))),
            'ports': len(set([r.get('origin_port_name') for r in data.get('routes', [])] + 
                           [r.get('destination_port_name') for r in data.get('routes', [])]))
        }
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        logger.error(f"Error getting file info: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_gtfs.route('/admin/gtfs/file/<path:filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    """
    Delete a GTFS file.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        file_path = os.path.join(scheduler.update_directory, secure_filename(filename))
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        # Delete the file
        os.remove(file_path)
        
        return jsonify({'success': True, 'message': 'File deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500