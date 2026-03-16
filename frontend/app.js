// ----------------------------
// shopping app frontend logic
// ----------------------------

// 1️⃣ Get token from browser storage (if user already logged in)
let token = localStorage.getItem("token");

// 2️⃣ Run when the page loads
window.onload = function () {
    // If a token exists, user is considered logged in
    if (token) {
        showApp();   // show main app screen
        loadItems(); // load items from backend
    } else {
        showLogin(); // otherwise, show login screen
    }
};

// ----------------------------
// Functions to show/hide screens
// ----------------------------

// Show main app, hide login
function showApp() {
    document.getElementById("login-container").style.display = "none";
    document.getElementById("app-container").style.display = "block";
}

// Show login, hide main app
function showLogin() {
    document.getElementById("login-container").style.display = "block";
    document.getElementById("app-container").style.display = "none";
}

// ----------------------------
// LOGIN
// ----------------------------

async function login() {
    // Get username and password values from input fields
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    try {
        // Send login request to backend
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }) // convert JS object to JSON
        });

        if (res.status !== 200) {
            // Login failed, show error message
            document.getElementById("login-error").innerText = "Invalid username or password";
            return;
        }

        // Parse JSON response from backend
        const data = await res.json();
        token = data.token;

        // Save token in local storage for future requests
        localStorage.setItem("token", token);

        // Show main app and load items
        showApp();
        loadItems();
    } catch (error) {
        console.error("Login error:", error);
        document.getElementById("login-error").innerText = "Server error, try again later";
    }
}

// ----------------------------
// LOGOUT
// ----------------------------

function logout() {
    token = null;                  // clear token in memory
    localStorage.removeItem("token"); // remove token from storage
    showLogin();                   // show login screen
}

// ----------------------------
// LOAD ITEMS FROM BACKEND
// ----------------------------

async function loadItems() {
    if (!token) return; // safety check

    try {
        // Send GET request to backend with Authorization header
        const res = await fetch("/api/items", {
            headers: { "Authorization": "Bearer " + token }
        });

        if (res.status === 401) {
            // Token invalid or expired → force logout
            logout();
            return;
        }

        const items = await res.json(); // parse JSON

        // Display items in the list
        const list = document.getElementById("items");
        list.innerHTML = ""; // clear old items

        items.forEach(i => {
            const li = document.createElement("li");
            li.textContent = i.name;
            list.appendChild(li);
        });
    } catch (error) {
        console.error("Load items error:", error);
    }
}

// ----------------------------
// ADD NEW ITEM
// ----------------------------

async function createItem() {
    const name = document.getElementById("itemName").value;
    if (!name || !token) return; // safety check

    try {
        // Send POST request to backend
        const res = await fetch("/api/items", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({ name })
        });

        if (res.status === 401) {
            // Token invalid → logout
            logout();
            return;
        }

        // Clear input field
        document.getElementById("itemName").value = "";

        // Reload items to show the new one
        loadItems();
    } catch (error) {
        console.error("Create item error:", error);
    }
}