from flask import Flask, request, jsonify, session
from flask_cors import CORS
import pandas as pd
import networkx as nx
from networkx.algorithms import community
import os
import uuid
from datetime import timedelta

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Enable credentials for session
app.secret_key = 'your_secret_key_here'  # Set a secret key for session
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# In-memory user storage (replace with database in production)
users = {
    "test@example.com": {
        "name": "Test User",
        "username": "testuser",
        "password": "password123",
        "mobile": "1234567890",
        "address": "123 Main St"
    }
}

# Password reset tokens
reset_tokens = {}

UPLOAD_FOLDER = 'uploads'
SAMPLE_FOLDER = 'samples'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SAMPLE_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------------- Helper Functions ----------------------

def load_graph_from_csv(file_path):
    """Load a graph from a CSV file"""
    df = pd.read_csv(file_path)
    G = nx.Graph()
    for _, row in df.iterrows():
        # Skip rows with missing values
        if pd.isna(row.iloc[0]) or pd.isna(row.iloc[1]):
            continue
        G.add_edge(row.iloc[0], row.iloc[1])
    return G

def analyze_graph(G):
    """Analyze the network graph and compute various metrics"""
    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()
    graph_density = nx.density(G)

    # Calculate average path length if graph is connected
    try:
        if nx.is_connected(G):
            avg_path_length = nx.average_shortest_path_length(G)
        else:
            avg_path_length = 0
    except nx.NetworkXError:
        avg_path_length = 0

    # Community detection
    communities = {}
    try:
        communities_generator = community.greedy_modularity_communities(G)
        for i, comm in enumerate(communities_generator):
            for node in comm:
                communities[node] = i
        modularity = community.modularity(G, communities_generator)
        community_count = len(communities_generator)
    except Exception:
        communities = {}
        modularity = 0
        community_count = 0

    # Centrality measures
    degree_centrality = nx.degree_centrality(G)
    betweenness_centrality = nx.betweenness_centrality(G)
    closeness_centrality = nx.closeness_centrality(G)
    
    # Eigenvector centrality might fail for disconnected graphs
    try:
        eigenvector_centrality = nx.eigenvector_centrality(G, max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        eigenvector_centrality = degree_centrality  # Fallback to degree centrality

    # Find most central nodes
    most_central = max(degree_centrality, key=degree_centrality.get) if degree_centrality else ""
    highest_betweenness = max(betweenness_centrality, key=betweenness_centrality.get) if betweenness_centrality else ""
    highest_closeness = max(closeness_centrality, key=closeness_centrality.get) if closeness_centrality else ""

    # Top nodes by centrality
    top_nodes = []
    for node in G.nodes():
        top_nodes.append({
            'node': node,
            'degree': degree_centrality.get(node, 0),
            'betweenness': betweenness_centrality.get(node, 0),
            'closeness': closeness_centrality.get(node, 0),
            'eigenvector': eigenvector_centrality.get(node, 0)
        })
    top_nodes = sorted(top_nodes, key=lambda x: x['degree'], reverse=True)[:5]

    # Link predictions
    predictions = []
    try:
        # Only compute predictions for smaller graphs
        if num_nodes < 1000:
            for u, v, p in nx.resource_allocation_index(G):
                if u != v and not G.has_edge(u, v):
                    probability = min(100, max(0, round(p * 100, 2)))
                    predictions.append({
                        'source': u,
                        'target': v,
                        'probability': probability
                    })
            predictions = sorted(predictions, key=lambda x: x['probability'], reverse=True)[:5]
    except Exception as e:
        print(f"Link prediction failed: {e}")


    # Graph diameter
    try:
        if nx.is_connected(G):
            graph_diameter = nx.diameter(G)
        else:
            graph_diameter = 0
    except nx.NetworkXError:
        graph_diameter = 0

    # Average degree
    degrees = [d for _, d in G.degree()]
    avg_degree = sum(degrees) / len(degrees) if degrees else 0

    return {
        'nodes': list(G.nodes()),
        'edges': list(G.edges()),
        'metrics': {
            'nodes': num_nodes,
            'edges': num_edges,
            'density': graph_density,
            'avg_path_length': avg_path_length,
            'modularity': modularity,
            'diameter': graph_diameter,
            'avg_degree': avg_degree
        },
        'degree_centrality': degree_centrality,
        'communities': communities,
        'community_count': community_count,
        'predictions': predictions,
        'top_nodes': top_nodes,
        'most_central': f"{most_central} ({degree_centrality.get(most_central, 0):.3f})" if most_central else "",
        'highest_betweenness': f"{highest_betweenness} ({betweenness_centrality.get(highest_betweenness, 0):.3f})" if highest_betweenness else "",
        'highest_closeness': f"{highest_closeness} ({closeness_centrality.get(highest_closeness, 0):.3f})" if highest_closeness else ""
    }

# ---------------------- Auth Routes ----------------------

@app.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password are required'}), 400
    
    user = users.get(email)
    
    if user and user['password'] == password:
        # Create session
        session['user'] = {
            'email': email,
            'name': user['name'],
            'username': user['username']
        }
        return jsonify({'success': True, 'user': session['user']})
    
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    """User logout endpoint"""
    # Clear session
    session.pop('user', None)
    return jsonify({'success': True})

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Password reset request endpoint"""
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    
    # Check if user exists
    if email not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    # Generate reset token (in real app, send email with this token)
    token = str(uuid.uuid4())
    reset_tokens[token] = email
    
    return jsonify({
        'success': True, 
        'message': 'Reset instructions sent'
    })

@app.route('/reset-password', methods=['POST'])
def reset_password():
    """Password reset endpoint"""
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('password')
    
    if not token or not new_password:
        return jsonify({'success': False, 'error': 'Token and password required'}), 400
    
    email = reset_tokens.get(token)
    if not email:
        return jsonify({'success': False, 'error': 'Invalid token'}), 400
    
    # Update password
    if email in users:
        users[email]['password'] = new_password
        del reset_tokens[token]
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/signup', methods=['POST'])
def signup():
    """User registration endpoint"""
    data = request.get_json()
    
    # Extract all fields
    name = data.get('name')
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    mobile = data.get('mobile')
    address = data.get('address')

    # Validate required fields
    if not all([name, username, email, password]):
        return jsonify({'success': False, 'error': 'Name, username, email, and password are required'}), 400

    # Check if email already exists
    if email in users:
        return jsonify({'success': False, 'error': 'User with this email already exists'}), 400
        
    # Check if username already exists
    if any(user['username'] == username for user in users.values()):
        return jsonify({'success': False, 'error': 'Username is already taken'}), 400

    # Store user data
    users[email] = {
        'name': name,
        'username': username,
        'password': password,
        'mobile': mobile or "",
        'address': address or ""
    }
    
    # Create session
    session['user'] = {
        'email': email,
        'name': name,
        'username': username
    }
    
    return jsonify({'success': True, 'user': session['user']})

@app.route('/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    if 'user' in session:
        return jsonify({'authenticated': True, 'user': session['user']})
    return jsonify({'authenticated': False})

# ---------------------- App Routes ----------------------

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and analysis"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    try:
        # Ensure upload directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Save file
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)
        
        # Load and analyze graph
        G = load_graph_from_csv(filename)
        result = analyze_graph(G)
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sample/<filename>', methods=['GET'])
def sample(filename):
    """Load sample data"""
    try:
        sample_path = os.path.join(SAMPLE_FOLDER, filename)
        
        # Security check: prevent path traversal
        if not os.path.abspath(sample_path).startswith(os.path.abspath(SAMPLE_FOLDER)):
            return jsonify({'error': 'Invalid file path'}), 400
            
        if not os.path.exists(sample_path):
            return jsonify({'error': 'Sample file not found'}), 404
        
        # Load and analyze sample graph
        G = load_graph_from_csv(sample_path)
        result = analyze_graph(G)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)