let token = localStorage.getItem("token");

// Run on page load
window.onload = function () {
    if (token) {
        showApp();
        loadItems();
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

    const res = await fetch("/api/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ username, password })
    });

    if (res.status !== 200) {
        document.getElementById("login-error").innerText = "Invalid login";
        return;
    }

    const data = await res.json();
    token = data.token;
    localStorage.setItem("token", token);  // store token for future requests

    showApp();
    loadItems();
}

// Logout
function logout() {
    token = null;
    localStorage.removeItem("token");
    showLogin();
}

// Load items
async function loadItems() {
    const res = await fetch("/api/items", {
        headers: { "Authorization": "Bearer " + token }
    });
    const items = await res.json();

    const list = document.getElementById("items");
    list.innerHTML = "";

    items.forEach(i => {
        const li = document.createElement("li");
        li.textContent = i.name;
        list.appendChild(li);
    });
}

// Add new item
async function createItem() {
    const name = document.getElementById("itemName").value;

    await fetch("/api/items", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token
        },
        body: JSON.stringify({ name })
    });

    document.getElementById("itemName").value = "";
    loadItems();
}