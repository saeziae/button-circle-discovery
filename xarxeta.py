import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import networkx as nx
import matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from tqdm import tqdm

BLACKLIST = ("0xc3.win",)  # I don't know why but this site stucks my script

# Set default headers for requests
requests.utils.default_headers = lambda: requests.structures.CaseInsensitiveDict({
    'User-Agent': 'curl/8.13.0'
})


def get_domain(url):
    return urlparse(url).netloc


def is_external(url, origin_domain):
    return get_domain(url) != origin_domain


def find_image_links(url):
    """Find <a><img></a> pairs that link to external sites"""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        external_links = []

        for a in soup.find_all('a', href=True):
            if a.find('img'):
                full_link = urljoin(url, a['href'])
                external_links.append(full_link)

        return external_links
    except Exception as e:
        # print(f"Error fetching {url}: {e}")
        return []


def check_image_link_back(target_url, origin_domain):
    """Check if this site has <a><img></a> linking back to origin domain"""
    if get_domain(target_url) in BLACKLIST:
        # print(f"Skipping blacklisted site: {target_url}")
        return False
    try:
        response = requests.get(target_url, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for a in soup.find_all('a', href=True):
            if a.find('img'):
                full_link = urljoin(target_url, a['href'])
                if origin_domain in full_link:
                    return True
        return False
    except Exception as e:
        # print(f"Error checking {target_url}: {e}")
        return False


def crawl(origin_site):
    if get_domain(origin_site) in BLACKLIST:
        # print(f"Skipping blacklisted site: {origin_site}")
        return origin_site, []
    origin_domain = get_domain(origin_site)
    # print(f"Origin domain: {origin_domain}")

    # 1. Get all <a><img></a> links to external sites
    external_links = find_image_links(origin_site)
    external_sites = set()

    for link in external_links:
        if is_external(link, origin_domain):
            parsed = urlparse(link)
            root_url = f"{parsed.scheme}://{parsed.netloc}"
            external_sites.add(root_url)
    # 2. Check if those sites have a backlink in <a><img>
    backlinking_sites = []

    def check(site):
        if check_image_link_back(site, origin_domain):
            # print(f"[YAY] Found backlink in {site}")
            return site
        return None

    with ThreadPoolExecutor(max_workers=32) as executor:
        future_to_site = {executor.submit(
            check, site): site for site in external_sites}
        for future in as_completed(future_to_site):
            result = future.result()
            if result:
                backlinking_sites.append(result)

    return origin_site, backlinking_sites


def main(url, depth=1):
    relations = []
    origins = set()
    current_url = (url,)
    for i in range(depth):
        current_url_tmp = set()
        # print(f"Scanning depth {i+1}...")
        for u in tqdm(current_url, desc=f"Depth {i+1}", unit="site"):
            if u in origins:
                continue  # dont scan again
            origins.add(u)
            org, dst = crawl(u)
            for d in dst:
                current_url_tmp.add(d)
                if d not in origins:
                    relations.append((get_domain(org), get_domain(d), i+1))
        current_url = current_url_tmp
    return relations


def visualize(relations):
    print("Visualizing relations...")
    G = nx.DiGraph()

    # Add edges and weights
    for source, target, weight in relations:
        G.add_edge(source, target, weight=weight)

    plt.figure(figsize=(24, 18))

    # Use a layout based on an undirected version for better spacing
    layout_graph = G.to_undirected()
    pos = nx.kamada_kawai_layout(layout_graph)

    # Add jittering to avoid node overlap
    for node in pos:
        jitter_x = random.uniform(-0.02, 0.02)
        jitter_y = random.uniform(-0.02, 0.02)
        pos[node] = (pos[node][0] + jitter_x, pos[node][1] + jitter_y)

    # Scale up the layout for better spacing
    for node in pos:
        pos[node] = (pos[node][0] * 2.5, pos[node][1] * 2.5)

    # Calculate node sizes and colors
    node_sizes = []
    ncolors = []
    for node in G.nodes():
        weights = [G[u][v]['weight'] for u, v in G.edges() if v == node]
        min_weight = min(weights) if weights else 0
        node_size = 5000 // (min_weight + 1)
        node_sizes.append(node_size)

        if min_weight <= 6:
            ncolors.append(['red', 'green', 'orange', 'skyblue',
                           'yellow', 'purple'][min_weight])
        else:
            ncolors.append('gray')

    edge_colors = ['#%06X' % random.randint(0, 0xFFFFFF) for _ in G.edges()]

    nx.draw(
        G, pos,
        with_labels=True,
        node_size=node_sizes,
        node_color=ncolors,
        edge_color=edge_colors,
        font_size=10,
        font_weight="bold",
        arrows=False
    )

    plt.title("Website Relations Graph (Optimized Layout)")
    plt.axis('off')
    plt.show()


if __name__ == "__main__":

    r = main("https://estela.moe", 3)

    # export relations to JSON
    with open("relations.json", "w") as f:
        json.dump(r, f)

    visualize(r)
