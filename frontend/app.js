async function loadItems() {
    const res = await fetch("/api/items");
    const items = await res.json();

    const list = document.getElementById("items");
    list.innerHTML = "";

    items.forEach(i => {
        const li = document.createElement("li");
        li.textContent = i.name;
        list.appendChild(li);
    });
}

async function createItem() {
    const name = document.getElementById("itemName").value;

    await fetch("/api/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    });

    loadItems();
}

loadItems();