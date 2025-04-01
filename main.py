from app import app, create_admin_user
from ext import db

# Create database tables and admin user if they don't exist
with app.app_context():
    db.create_all()
    create_admin_user()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
