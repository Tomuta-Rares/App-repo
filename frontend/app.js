// Check if a token exists in browser storage
let token = localStorage.getItem("token");

// Run on page load
window.onload = function () {
    if (token) {
        // Token exists → show main app
        showApp();
        loadItems();
    } else {
        // No token → show login
        showLogin();
    }
};

// Show main app and hide login
function showApp() {
    document.getElementById("login-container").style.display = "none";
    document.getElementById("app-container").style.display = "block";
}

// Show login and hide main app
function showLogin() {
    document.getElementById("login-container").style.display = "block";
    document.getElementById("app-container").style.display = "none";
}

// Login function
async function login() {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        if (!res.ok) {
            document.getElementById("login-error").innerText = "Invalid login";
            return;
        }

        const data = await res.json();
        token = data.token;
        localStorage.setItem("token", token); // save token for future requests

        // Hide login, show main app
        showApp();
        loadItems();
    } catch (err) {
        document.getElementById("login-error").innerText = "Login failed, try again.";
        console.error(err);
    }
}

// Logout function
function logout() {
    token = null;
    localStorage.removeItem("token");
    showLogin();
}

// Load all items from backend
async function loadItems() {
    if (!token) return;

    try {
        const res = await fetch("/api/items", {
            headers: { "Authorization": "Bearer " + token }
        });

        if (!res.ok) {
            console.error("Failed to load items");
            return;
        }

        const items = await res.json();
        const list = document.getElementById("items");
        list.innerHTML = "";

        items.forEach(i => {
            const li = document.createElement("li");
            li.textContent = i.name;
            list.appendChild(li);
        });
    } catch (err) {
        console.error(err);
    }
}

// Add a new item
async function createItem() {
    const name = document.getElementById("itemName").value;
    if (!name) return;

    try {
        const res = await fetch("/api/items", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({ name })
        });

        if (!res.ok) {
            alert("Failed to add item");
            return;
        }

        document.getElementById("itemName").value = "";
        loadItems();
    } catch (err) {
        console.error(err);
    }
}