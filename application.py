import os

from flask import Flask, session, request, render_template, flash, redirect, url_for, jsonify, json
from datetime import datetime
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from helper import login_required
import requests

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.context_processor
def inject_user():
    username = session.get("username")
    return dict(username=username)

@app.route("/", methods=['GET','POST'])
@login_required
def index():
    # get username stored in session
    username=session.get('username') 
    print(username)
    # fetch all books for display / slice first element ISBN
    all_books = db.execute("SELECT * FROM books").fetchmany(6)[1:]
    # search function for books
    if request.method == "POST":
        searchQuery = request.form.get("searchQuery")
        # return value from the search
        searchResult = db.execute("SELECT isbn, author, title FROM books WHERE isbn iLIKE '%"+searchQuery+"%' OR author iLIKE '%"+searchQuery+"%' OR title iLIKE '%"+searchQuery+"%'").fetchall()
        # add search result to the list
        session["books"] = []
        # add the each result to the list
        for i in searchResult:
            session["books"].append(i)
        if len(session["books"])==0:
            return "No list!"
        return render_template("index.html", books = session["books"], searchQuery = searchQuery, username = username)
    return render_template("index.html", all_books=all_books )

@app.route("/login", methods=['GET','POST'])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        # check if user exists
        u = db.execute("SELECT username, email, password FROM users WHERE email = :email", {"email": email}).fetchone()
        if u is None or not check_password_hash(u.password, request.form.get("password")):
            return "Wrong credential"
        session["username"] = u.username
        return redirect(url_for('index', message="Login successful!", username=session["username"]))
    session.pop('message', None)
    return render_template("login.html")

@app.route("/register", methods=['GET','POST'])
def register():
    if request.method == "POST":
        session['username'] = request.form.get('username')
        # check if username and email exist
        username = request.form.get("username")
        email = request.form.get("email")
        u = db.execute("SELECT username, email FROM users WHERE username = :username",{"username": username}).fetchone()
        if u.username is not None:
            return "username already exists"
        #u = db.execute("SELECT email FROM users WHERE email = :email",{"email": email}).fetchone()
        elif u.email is not None:
            return "email already exists"
        # check if password and confirm_password match
        if request.form.get("password") != request.form.get("confirm_password"):
            return "password do not match"
        # insert user if statisfy all requirements
        hashed_password = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, email, password) VALUES (:username, :email, :password)",
        {"username": username, "email": email, "password": hashed_password})
        db.commit()
        return redirect("/login")
    # render login page once registerd
    return render_template("register.html")

@app.route('/book/<string:isbn>', methods = ['POST','GET'])
@login_required
def book(isbn):
    #get username stored in session
    username = session.get('username')
    #import columns from database 
    res = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    #import api from Goodreads (stats) 
    r = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "L3FHyOR3IhCo3kctcUz3zg", "isbns": isbn})
    if r.status_code != 200:
      raise ValueError
    average_rating=r.json()["books"][0]["average_rating"]
    work_ratings_count=r.json()["books"][0]["work_ratings_count"]
    work_text_reviews_count=r.json()["books"][0]["work_text_reviews_count"]
    username = session.get("username")
    # get book's id
    book_id, = db.execute("SELECT id FROM books WHERE isbn = :isbn",{"isbn":isbn}).fetchone()
    # review submission
    if request.method == "POST":
        # get form data and date & time 
        review = request.form.get("comment")
        rating = request.form.get("rating")
        date = datetime.now()
        # fetch user's id from users table
        user_id, = db.execute("SELECT id FROM users WHERE username = :username",{"username":username}).fetchone()
        # add review to the review table
        db.execute("INSERT INTO reviews (book_id, user_id, review, rating, date) VALUES (:book_id, :user_id, :review, :rating, :date)", {"date":date, "review":review, "rating":rating, "user_id":user_id, "book_id":book_id})
        db.commit()
    # add reviews to the page using for loop
    reviews = db.execute("SELECT * FROM reviews JOIN users ON reviews.user_id = users.id WHERE book_id = :book_id",
            {"book_id": book_id}).fetchall()
    return render_template("book.html", reviews_count = work_text_reviews_count, ratings_count = work_ratings_count, average_rating = average_rating, username = username, reviews = reviews, book_title = res.title, isbn = isbn )
    
@app.route('/api/<string:isbn>', methods = ['GET'])
def isbn(isbn):
    #import api from Goodreads (stats)
    r = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "L3FHyOR3IhCo3kctcUz3zg", "isbns": isbn})
    res = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    if r.status_code != 200:
        raise ValueError
    work_ratings_count=r.json()["books"][0]["work_ratings_count"]
    work_text_reviews_count=r.json()["books"][0]["work_text_reviews_count"]
    return jsonify
    ({
        "title": res.title,
        "author": res.author,
        "year": res.year,
        "isbn": res.isbn,
        "work_ratings_count": work_ratings_count,
        "work_text_reviews_count": work_text_reviews_count,
    })

@app.route('/logout')
@login_required
def logout():
   # remove the username from the session if it is there
   session.pop('username', None)
   return redirect(url_for('login'))