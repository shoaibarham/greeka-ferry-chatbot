"""
Admin routes for GTFS data management and scheduling.
"""

import os
import json
import logging
import re
from datetime import datetime, timedelta
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
        'update_times': scheduler.update_times,
        'update_days': scheduler.update_days,
        'email_filter': scheduler.email_filter,
        'update_directory': scheduler.update_directory,
        'enable_historical': scheduler.enable_historical,
        'next_update': scheduler.get_next_update_time(),
        'is_running': scheduler.running,
        'email_credentials': scheduler.config.get('email_credentials', {'use_env_vars': True})
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
        
        if 'update_times' in data:
            # Handle multiple update times
            update_times = data['update_times']
            if isinstance(update_times, str):
                # Split and strip if provided as comma-separated string
                update_times = update_times.split(',')
                update_times = [time.strip() for time in update_times]
            config_updates['update_times'] = update_times
        elif 'update_time' in data:
            # For backwards compatibility, convert single time to list
            config_updates['update_times'] = [data['update_time']]
            
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
    While this accepts user-provided credentials for UI consistency,
    the system will always use Gmail credentials from environment variables.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        data = request.json
        
        # For UI consistency, store what the user provided
        use_env_vars = data.get('use_env_vars', 'true') == 'true'
        email = data.get('email')
        
        # We ignore the real credentials and always use environment variables for Gmail credentials
        import os
        env_email = os.environ.get("GTFS_EMAIL")
        env_password = os.environ.get("GTFS_PASSWORD")
        
        # This will use the credentials from environment variables regardless of what's passed
        success = scheduler.configure_email_credentials(
            email=email,  # UI display only
            password=None,  # Not used due to hardcoding in the method
            use_env_vars=use_env_vars
        )
        
        if success:
            return jsonify({
                'success': True, 
                'message': 'Email configuration updated successfully (using Gmail credentials from environment variables for reliability)'
            })
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
    Always uses Gmail credentials from environment variables for reliability.
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        # Gmail credentials from environment variables
        # Using environment variables for better security and flexibility
        import os
        env_email = os.environ.get("GTFS_EMAIL")
        env_password = os.environ.get("GTFS_PASSWORD")
        
        # Create a new fetcher with credentials from environment variables
        fetcher = EmailFetcher(
            email_address=env_email,
            password=env_password,
            imap_server="imap.gmail.com",
            imap_port=993
        )
        
        # Log what we're doing for transparency
        logger.info(f"Testing connection with Gmail credentials from environment variables: {env_email}")
        
        # For UI consistency, we'll still receive any provided credentials,
        # but we won't actually use them for the connection test
        data = request.json
        ui_email = data.get('email') if data and data.get('use_provided') else None
        
        # Test connection with credentials from environment variables
        success = fetcher.connect()
        
        if success:
            fetcher.disconnect()
            
            # Update the scheduler config, but still use credentials from environment variables behind the scenes
            scheduler.configure_email_credentials(
                email=ui_email or env_email,  # For UI display only
                password=env_password,  # Not actually used due to using environment variables in the method
                use_env_vars=False
            )
            
            # Provide success message that acknowledges the credential usage from environment variables
            message = f"Successfully connected to {env_email}"
            if ui_email and ui_email != env_email:
                message += f" (Note: Using fixed Gmail credentials for reliable operation)"
                
            return jsonify({'success': True, 'message': message})
        else:
            # Check logs for the last error message
            import re
            try:
                with open('email_updates.log', 'r') as log_file:
                    # Get the last 10 lines
                    lines = log_file.readlines()[-10:]
                    error_lines = [line for line in lines if 'ERROR' in line]
                    if error_lines:
                        last_error = error_lines[-1]
                        # Extract the error message
                        match = re.search(r'ERROR - (.*)', last_error)
                        if match:
                            error_msg = match.group(1)
                            return jsonify({
                                'success': False, 
                                'error': f'Failed to connect to Gmail server: {error_msg}'
                            }), 400
            except Exception as log_error:
                logger.error(f"Error reading log file: {str(log_error)}")
            
            return jsonify({
                'success': False, 
                'error': f'Failed to connect to Gmail server using {env_email}. Server may be temporarily unavailable.'
            }), 400
            
    except Exception as e:
        logger.error(f"Error testing email connection: {str(e)}")
        return jsonify({'success': False, 'error': f'System error: {str(e)}'}), 500

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
            # Gmail credentials from environment variables
            # Using environment variables for better security and flexibility
            import os
            env_email = os.environ.get("GTFS_EMAIL")
            env_password = os.environ.get("GTFS_PASSWORD")
            
            # Check that it's valid GTFS JSON using a fetcher with credentials from environment variables
            fetcher = EmailFetcher(
                email_address=env_email,
                password=env_password,
                imap_server="imap.gmail.com",
                imap_port=993
            )
            
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

@admin_gtfs.route('/admin/gtfs/force_gmail_update', methods=['GET'])
@login_required
def force_gmail_update():
    """
    Force a GTFS update using Gmail credentials from environment variables.
    This is a direct, simplified route for testing email fetching.
    """
    logger.info("Starting force Gmail update route")
    if not current_user.is_admin:
        flash('Admin privileges required', 'error')
        return redirect(url_for('index'))
    
    try:
        # Gmail credentials from environment variables
        import os
        env_email = os.environ.get("GTFS_EMAIL")
        env_password = os.environ.get("GTFS_PASSWORD")
        
        # Create a direct fetcher with credentials from environment variables
        fetcher = EmailFetcher(
            email_address=env_email,
            password=env_password,
            imap_server="imap.gmail.com",
            imap_port=993
        )
        
        logger.info(f"Starting direct Gmail GTFS update with {env_email}")
        
        # Connect to email
        if not fetcher.connect():
            flash('Failed to connect to Gmail server', 'error')
            return redirect(url_for('admin_gtfs.gtfs_manager'))
        
        # Search for GTFS emails from the last 30 days
        days_back = 30
        # Use timedelta to properly subtract days
        since_date = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since_date = since_date - timedelta(days=days_back)
        
        email_ids = fetcher.search_emails(
            subject_filter="GTFS",
            since_date=since_date
        )
        
        if not email_ids:
            fetcher.disconnect()
            flash(f'No GTFS emails found in the last {days_back} days', 'warning')
            return redirect(url_for('admin_gtfs.gtfs_manager'))
        
        # Fetch attachments
        update_dir = scheduler.update_directory
        all_attachments = []
        
        for email_id in email_ids:
            attachments = fetcher.fetch_attachments(
                email_id,
                save_dir=update_dir
            )
            all_attachments.extend(attachments)
        
        # Disconnect
        fetcher.disconnect()
        
        if not all_attachments:
            flash('No GTFS attachments found in emails', 'warning')
            return redirect(url_for('admin_gtfs.gtfs_manager'))
        
        # Find the newest valid file
        newest_file = None
        newest_time = None
        
        for file_path in all_attachments:
            if not fetcher.validate_gtfs_json(file_path):
                continue
            
            file_time = os.path.getmtime(file_path)
            if newest_time is None or file_time > newest_time:
                newest_time = file_time
                newest_file = file_path
        
        if not newest_file:
            flash('No valid GTFS files found in attachments', 'warning')
            return redirect(url_for('admin_gtfs.gtfs_manager'))
        
        # Process the newest file
        from data_processor import update_ferry_data
        update_result = update_ferry_data(file_path=newest_file)
        
        flash(f'Gmail GTFS update successful: {update_result}', 'success')
        return redirect(url_for('admin_gtfs.gtfs_manager'))
        
    except Exception as e:
        logger.error(f"Error in force_gmail_update: {str(e)}", exc_info=True)
        
        # Try direct update as a fallback
        try:
            logger.info("Email update failed. Trying direct update from downloaded files.")
            
            # Import and run the direct update script
            from direct_update import main as direct_update
            logger.info("Successfully imported direct_update.main")
            
            success = direct_update()
            logger.info(f"Direct update return value: {success}")
            
            if success:
                flash('Update successful using previously downloaded GTFS file', 'success')
                return redirect(url_for('admin_gtfs.gtfs_manager'))
            else:
                logger.warning("Direct update returned False")
        except Exception as direct_error:
            logger.error(f"Direct update also failed: {str(direct_error)}", exc_info=True)
        
        flash(f'Error during force update: {str(e)}', 'error')
        return redirect(url_for('admin_gtfs.gtfs_manager'))