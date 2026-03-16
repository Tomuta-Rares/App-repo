// Get token from localStorage if exists
let token = localStorage.getItem("token");

// Run when page loads
window.onload = function () {
    if (token) {
        showApp();   // show main app if already logged in
        loadItems(); // load items from backend
    }
};

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

// LOGIN FUNCTION
async function login() {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        if (res.status !== 200) {
            document.getElementById("login-error").innerText = "Invalid login";
            return;
        }

        const data = await res.json();
        token = data.token;

        localStorage.setItem("token", token); // store token for future API calls

        showApp();
        loadItems();
    } catch (err) {
        document.getElementById("login-error").innerText = "Error connecting to server";
        console.error(err);
    }
}

// LOGOUT FUNCTION
function logout() {
    token = null;
    localStorage.removeItem("token");
    showLogin();
}

// LOAD ITEMS FROM BACKEND
async function loadItems() {
    if (!token) return;

    try {
        const res = await fetch("/api/items", {
            headers: { "Authorization": "Bearer " + token }
        });

        if (!res.ok) {
            console.error("Failed to fetch items:", res.status);
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
        console.error("Error loading items:", err);
    }
}

// ADD NEW ITEM
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
            console.error("Failed to create item:", res.status);
            return;
        }

        document.getElementById("itemName").value = "";
        loadItems();
    } catch (err) {
        console.error("Error creating item:", err);
    }
}