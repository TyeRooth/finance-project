import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from datetime import datetime
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


@app.route("/")
@login_required
def index():
    #Try planning out your attacks with pseudocode before you start typing
    """Show portfolio of stocks"""
    # Collect username as it is common across all database tables
    user = db.execute("SELECT username FROM users WHERE id = (?)", session["user_id"])[0]['username']
    
    #Select all symbols and share counts from owned table that have the username.  This should give me a dictionary list that I can insert into values of homepage.
    owned = db.execute("SELECT symbol, shares, buyprice FROM owned WHERE username = (?)", user)
    
    #Clear homepage table rows from previous site visits
    db.execute("DELETE FROM homepage WHERE username = (?)", user)
    
    # In loop, there needs to be a conditional for whether that symbol already has a spot in homepage with the user so there are not multiple inserts.
    # Loop through list of dicts derived from previous SELECTs.  Each loop should generate one line in home page
    # Heads Up !!! Use single quotes when dealing with dict lists
    for x in range(len(owned)):
        symbol = owned[x]['symbol']
        price = lookup(symbol)['price']
        shares = owned[x]['shares']
        value = price * shares
        
        #Find return of stocks using buyprice and price
        buyprice = owned[x]['buyprice']
        interest = round((price - buyprice) / 100, 2);
        
        db.execute(
            "INSERT INTO homepage (username, symbol, shares, price, value, return) VALUES (?, ?, ?, ?, ?, ?)",
            user,
            symbol,
            shares,
            price,
            value,
            interest
        )
    
    # Select all from the homepage which will then create a list of dicts
    stocks = db.execute("SELECT * FROM homepage WHERE username=?", user)
    
    #Grab cash value to display
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])[0]['cash']
    
    #Grab total value including stocks and cash
    values = db.execute("SELECT value FROM homepage WHERE username = ?", user)
    stocks_value = 0
    for x in range(len(values)):
        stocks_value = stocks_value + values[x]['value']
    value = cash + stocks_value
    
    # Put the dicts into template
    return render_template("index.html", stocks = stocks, cash = cash, value = value)  
    
    # Edit index.html to make the table look prettier
    
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        #Check whether symbol was inputted
        if not request.form.get("symbol"):
            return apology("Must provide symbol")

        #Grab stock
        stock = lookup(request.form.get("symbol"))

        #Check whether stock exists
        if not stock:
            return apology ("Stock does not exist")

        # Get attributes of stock
        symbol = stock["symbol"]
        price = stock["price"]
        company = stock["name"]

        # Check whether shares bought is a pos int
        share = request.form.get("shares")
        if float(share) / round(float(share)) != 1:
            return apology ("Fractional shares not allowed")
        shares = int(share)
        if shares < 1:
            return apology ("Invalid number of shares bought")

        # Collect Information about Price and Users
        cost = shares * price
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        # Check to ensure user has enough cash in their account to make purchase
        if cost > cash:
            return apology ("Not enough funds for purchase")
            
        #Add user name to make tables joinable
        username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        
        # Add transaction to history table
        date_time = datetime.now()
        db.execute(
            "INSERT INTO history (username, type, symbol, price, share, datetime) VALUES (?, 'BOUGHT', ?, ?, ?, ?)",
            username,
            symbol,
            price,
            shares,
            date_time
        )
        
        # Make a section for checking whether this user already has some of this symbol
        owned = db.execute("SELECT symbol FROM owned WHERE username = ?", username)
        for x in range(len(owned)):
            if symbol in owned[x]['symbol']:
                previous_shares = db.execute("SELECT shares FROM owned WHERE symbol = (?) AND username = (?)", symbol, username)[0]['shares']
                new_shares = previous_shares + shares
                db.execute("UPDATE owned SET shares = (?) WHERE symbol = (?) AND username = (?)", new_shares, symbol, username)
                
                #Update new average buy price
                prev_buy = db.execute("SELECT buyprice FROM owned WHERE symbol = ?", symbol)[0]['buyprice']
                avg_share = (previous_shares * prev_buy + shares * price)/(previous_shares + shares)
                db.execute("UPDATE owned SET buyprice = (?) WHERE symbol = (?) AND username = (?)", avg_share, symbol, username)
                return redirect ("/")
                
                # I have to fix a bug where the buy price has now been affected by updating the share count.

        #Make the purchase on the users account
        else:
            remainder = cash - cost
            db.execute(
                "INSERT INTO owned (symbol, company, buyprice, shares, username) VALUES (?, ?, ?, ?, ?)",
                symbol,
                company,
                price,
                shares,
                username
            )
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", remainder, session["user_id"])

        #Go back to index page
        return redirect ("/")
    else:
        return render_template("buy.html")
    return apology("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    #Add history sections to Buy and Sell POST functions that collects all the needed info
    #SELECT the table for history to be inputted into template
    user = db.execute ("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    stocks = db.execute("SELECT * FROM history WHERE username = ?", user)
    
    #Render template for history.html which features a table displaying the transactions
    return render_template("history.html", stocks=stocks)


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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

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

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # Set up post condition for lookup function
    if request.method == "POST":
        symb = lookup(request.form.get("symbol"))
        if not symb:
            return apology("stock does not exist", 400)
        return render_template("quoted.html", symb=symb)
    else:
        return render_template("quote.html")

        #Currently has error where quoted does not exist

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Set up post condition where new registrants are submitted
    if request.method == "POST":

        #Check whether username was given
        if not request.form.get("username"):
            return apology("must provide username")

        #Check whether password was given
        elif not request.form.get("password"):
            return apology("must provide password")

        #Check whether password confirmation was given
        elif not request.form.get("confirmation"):
            return apology("must confirm password")

        #Check whether username exists
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) == 1:
            return apology("username already taken")

        #Check that password and confirmation are the same
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match")
        
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?) ", request.form.get("username"), generate_password_hash(request.form.get("password")))

        return redirect("/")
    else:
        return render_template("register.html")
    return apology("TODO")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    #Find specific account for both post and get methods
    user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    if request.method == "POST":
        #Access form inputs
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        
        # Check whether user selected a stock
        if not request.form.get("symbol"):
            return apology("Please Select Stock to Sell")
            
        #Check whether user inputted share number and has enough shares to sell
        if not request.form.get("shares"):
            return apology("Please input number of shares to sell")
            
        prev_shares = db.execute("SELECT shares FROM homepage WHERE symbol = (?) AND username = (?)", symbol, user)[0]['shares']
        if prev_shares < shares:
            return apology("Does not own enough shares to sell")
            
        #Add new transaction to history table
        price = lookup(symbol)["price"]
        date_time = datetime.now()
        db.execute(
            "INSERT INTO history (username, type, symbol, price, share, datetime) VALUES (?, 'SOLD', ?, ?, ?, ?)",
            user,
            symbol,
            price,
            shares,
            date_time
        )
        
        #Change the cash in the account to match the sale
        sell_price = db.execute("SELECT price FROM homepage WHERE symbol = (?) AND username = (?)", symbol, user)[0]['price']
        sell = sell_price * shares
        prev_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
        cash = prev_cash + sell
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", cash, session["user_id"])
        
        #Change the number of shares the individual owns
        new_shares = prev_shares - shares
        db.execute("UPDATE owned SET shares = (?) WHERE symbol = (?) AND username = (?)", new_shares, symbol, user)
        
        #Drop any rows in homepage that have zero shares
        if new_shares == 0:
            db.execute("DELETE owned WHERE username = (?) AND symbol = (?)", user, symbol)
            
        # Return to index page
        return redirect("/")
    else:
        # Select for stocks owned by the current user to display in select menu
        symbols = db.execute("SELECT symbol FROM homepage WHERE username = ?", user)
        return render_template("sell.html", symbols=symbols)
        
def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)