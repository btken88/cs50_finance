import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get user's current cash
    cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id'])

    # Get user's current portfolio holdings
    holdings = db.execute("SELECT symbol, SUM(shares), price, name FROM transactions WHERE id=:id GROUP BY symbol", id=session['user_id'])

    # Update holding prices
    value = cash[0]['cash']
    for row in holdings:
        row['price'] = lookup(row['symbol'])['price']
        value = value + row['price']*row['SUM(shares)']
    return render_template("index.html", holdings=holdings, cash=usd(cash[0]['cash']), value=usd(value))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # If page reached by post
    if request.method == "POST":
        # Find out how much cash the user has
        cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id'])

        # Get number of shares requested by usertry:
        try:
            shares = int(request.form.get('shares'))
        except ValueError:
            return apology("provide an interger for shares")

        # If there isn't input or input 0 or less request input again
        if not shares or shares <=0:
            return apology("please provide a valid number of shares")

        # Lookup the stock symbol
        quote = lookup(request.form.get("symbol"))
        if not quote:
            return apology("please provide a valid stock symbol")

        # Check if cash available will cover the purchase
        if float(cash[0]['cash']) < int(shares)*float(quote['price']):
            return apology("Not enough cash")

        # Insert transaction into table
        db.execute("INSERT INTO transactions (id, symbol, shares, price, type, name) VALUES (:id, :symbol, :shares, :price, :type, :name)",
                   id=session['user_id'], symbol=quote['symbol'], shares=shares, price=quote['price'], type="buy", name=quote['name'])

        # Change available cash amount
        db.execute("UPDATE users set cash=cash-:n WHERE id=:id", n=shares*quote['price'], id=session['user_id'])

        # Redirect to homepage
        return redirect("/")

    # If not post, show buy form
    return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    username = request.args.get("username", '')
    current = []
    for row in db.execute("SELECT username FROM users"):
        current.append(row["username"])
    """Return true if username available, else false, in JSON format"""
    if len(username) >=1 and username not in current:
        return jsonify(True)
    else:
        return jsonify(False)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get user's portfolio history
    holdings = db.execute("SELECT * FROM transactions WHERE id=:id", id=session['user_id'])
    return render_template("history.html", holdings=holdings)


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == 'POST':
        # Create dict using user input symbol
        quote = lookup(request.form.get("symbol"))

        # Confirm input returned a valid quote
        if not quote:
            return apology("please provide a valid stock symbol")

        # Return page with values for name, symbol, and price
        return render_template("quoted.html", name=quote['name'], symbol=quote['symbol'], price=usd(quote['price']))

    # If get, return initial template.
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # If page is reached by post
    if request.method == 'POST':

        # Ensure user entered username, password, and password confirmation
        if not request.form.get("username"):
            return apology("must provide username")

        elif not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide password")

        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords must match")

        # Hash user password
        hash = generate_password_hash(request.form.get("password"))

        # Insert the new user into users, storing a hash of the user’s password
        result = db.execute("INSERT INTO users ('username', 'hash') VALUES (:username, :hash)",
                            username=request.form.get('username'), hash=hash)
        if not result:
            return apology("Username not available.")

        # Store user id in session to log user in.
        session["user_id"] = db.execute("SELECT id FROM users WHERE username = :username",
                                        username=request.form.get("username"))[0]['id']

        # Redirect to homepage
        return redirect("/")

    # If not post, show the registration pages
    return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Get number of shares requested by user and validate
        shares = int(request.form.get('shares'))
        if not shares or shares <=0:
            return apology("please provide a valid number of shares")

        # Get number of shares of selected holding
        held = db.execute("SELECT SUM(shares) FROM transactions WHERE id=:id GROUP BY symbol HAVING symbol=:symbol",
                          id=session['user_id'], symbol=request.form.get('symbol'))

        if held[0]['SUM(shares)'] < shares:
            return apology("you don't own that many shares")

        # Lookup information on stock selected
        quote = lookup(request.form.get('symbol'))

        # Insert sale information into transaction table
        db.execute("INSERT INTO transactions (id, symbol, shares, price, type, name) VALUES (:id, :symbol, :shares, :price, :type, :name)",
                   id=session['user_id'], symbol=quote['symbol'], shares=-shares, price=quote['price'], type="sell", name=quote['name'])

        # Change available cash amount
        db.execute("UPDATE users set cash=cash+:n WHERE id=:id", n=shares*quote['price'], id=session['user_id'])

        return redirect("/")

    else:
        # Get user's current portfolio holdings
        holdings = db.execute("SELECT symbol, SUM(shares), price, name FROM transactions WHERE id=:id GROUP BY symbol", id=session['user_id'])
        return render_template("sell.html", holdings=holdings)


@app.route("/deposit", methods=["POST"])
@login_required
def deposit():
    db.execute("UPDATE users set cash=cash+:n WHERE id=:id", n=request.form.get("cash"), id=session['user_id'])
    return redirect('/')


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
