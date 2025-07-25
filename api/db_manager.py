#!/usr/bin/env python3
"""
Database Management Script for Spotify Mood Tracker

This script helps you manage your database:
- Initialize/create tables
- View statistics
- Reset database (careful!)
- Export data
"""

import os
import sys
from datetime import datetime, timedelta
from collections import Counter

# Add the parent directory to sys.path so we can import from app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import your app and models
from api.app import app
from api.models import db, User, Track, Listen

def init_db():
    """Initialize the database and create all tables"""
    with app.app_context():
        db.create_all()
        print("Database initialized successfully!")
        print(f"Database location: {app.config['SQLALCHEMY_DATABASE_URI']}")

def show_stats():
    """Show database statistics"""
    with app.app_context():
        users_count = User.query.count()
        tracks_count = Track.query.count()
        listens_count = Listen.query.count()
        
        print("\n📊 DATABASE STATISTICS")
        print("=" * 30)
        print(f"👥 Users: {users_count}")
        print(f"🎵 Unique Tracks: {tracks_count}")
        print(f"🎧 Total Listens: {listens_count}")
        
        if users_count > 0:
            print(f"\nAverage listens per user: {listens_count / users_count:.1f}")
        
        if tracks_count > 0:
            # Show mood distribution
            moods = db.session.query(Track.mood).filter(Track.mood.isnot(None)).all()
            mood_counts = Counter([mood[0] for mood in moods])
            
            print(f"\nMOOD DISTRIBUTION:")
            for mood, count in mood_counts.most_common():
                percentage = (count / len(moods)) * 100
                print(f"   {mood}: {count} ({percentage:.1f}%)")
        
        # Show recent activity
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_listens = Listen.query.filter(Listen.played_at >= week_ago).count()
        print(f"\nRecent activity (last 7 days): {recent_listens} listens")

def show_users():
    """Show all users in the database"""
    with app.app_context():
        users = User.query.all()
        
        print(f"\n👥 USERS ({len(users)} total)")
        print("=" * 50)
        
        for user in users:
            listens_count = Listen.query.filter_by(user_id=user.id).count()
            last_activity = db.session.query(Listen.played_at).filter_by(user_id=user.id).order_by(Listen.played_at.desc()).first()
            
            print(f"ID: {user.id}")
            print(f"Spotify ID: {user.spotify_id}")
            print(f"Total Listens: {listens_count}")
            print(f"Last Activity: {last_activity[0] if last_activity else 'Never'}")
            print(f"Created: {user.created_at}")
            print("-" * 30)

def reset_db():
    """Reset the entire database (BE CAREFUL!)"""
    print("⚠️  WARNING: This will DELETE ALL DATA!")
    confirm = input("Type 'DELETE' to confirm: ")
    
    if confirm == 'DELETE':
        with app.app_context():
            db.drop_all()
            db.create_all()
            print("🗑️  Database reset successfully!")
    else:
        print("Reset cancelled.")

def export_data(user_spotify_id=None):
    """Export user data to CSV"""
    import csv
    
    with app.app_context():
        if user_spotify_id:
            user = User.query.filter_by(spotify_id=user_spotify_id).first()
            if not user:
                print(f"User {user_spotify_id} not found!")
                return
            users = [user]
            filename = f"spotify_mood_export_{user_spotify_id}.csv"
        else:
            users = User.query.all()
            filename = "spotify_mood_export_all.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['User', 'Track Name', 'Artist', 'Mood', 'Played At'])
            
            for user in users:
                listens = db.session.query(Listen, Track).join(Track).filter(
                    Listen.user_id == user.id
                ).order_by(Listen.played_at.desc()).all()
                
                for listen, track in listens:
                    writer.writerow([
                        user.spotify_id,
                        track.name,
                        track.artist,
                        track.mood,
                        listen.played_at.isoformat()
                    ])
        
        print(f"📁 Data exported to {filename}")

def main():
    """Main menu"""
    while True:
        print("\n🎵 SPOTIFY MOOD TRACKER - DATABASE MANAGER")
        print("=" * 45)
        print("1. Initialize Database")
        print("2. Show Statistics")
        print("3. Show Users")
        print("4. Export Data (All Users)")
        print("5. Export Data (Specific User)")
        print("6. Reset Database (⚠️ DANGEROUS)")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-6): ").strip()
        
        if choice == '1':
            init_db()
        elif choice == '2':
            show_stats()
        elif choice == '3':
            show_users()
        elif choice == '4':
            export_data()
        elif choice == '5':
            spotify_id = input("Enter Spotify user ID: ").strip()
            export_data(spotify_id)
        elif choice == '6':
            reset_db()
        elif choice == '0':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == '__main__':
    main()