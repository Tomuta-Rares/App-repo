const keycloak = new Keycloak({
    url: "https://auth.local:8443/auth/",
    realm: "devops-lvlup",
    clientId: "shopping-frontend"
});

async function initKeycloak() {
    const authenticated = await keycloak.init({
        onLoad: "login-required",
        checkLoginIframe: false
    });

    if (!authenticated) {
        console.log("Not authenticated");
        return;
    }

    console.log("Authenticated!");
    console.log("User:", keycloak.tokenParsed.preferred_username);
}

async function loadItems() {
    const res = await fetch("/api/items", {
        headers: {
            Authorization: "Bearer " + keycloak.token
        }
    });

    const data = await res.json();

    const list = document.getElementById("items");
    list.innerHTML = "";

    data.items.forEach(i => {
        const li = document.createElement("li");
        li.textContent = i.name;
        list.appendChild(li);
    });
}

async function createItem() {
    const name = document.getElementById("itemName").value;

    await fetch("/api/items", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + keycloak.token
        },
        body: JSON.stringify({ name })
    });

    loadItems();
}

function logout() {
    keycloak.logout({
        redirectUri: "https://shopping.local:8443"
    });
}

// INIT APP
initKeycloak().then(() => {
    loadItems();
});