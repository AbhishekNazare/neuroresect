"""Strength-weighted graph metrics with explicit disconnected-pair conventions."""

from __future__ import annotations

import networkx as nx
import numpy as np
from scipy.sparse.csgraph import shortest_path

from neurocore.validation import validate_matrix


def global_metrics(matrix) -> dict:
    weights = validate_matrix(matrix)
    n = len(weights)
    graph = nx.from_numpy_array(weights)
    distances = np.zeros_like(weights)
    np.divide(1.0, weights, out=distances, where=weights > 0)
    paths = shortest_path(distances, directed=False, unweighted=False)
    off_diagonal = ~np.eye(n, dtype=bool)
    reachable = np.isfinite(paths) & off_diagonal
    inverse = np.zeros_like(paths)
    np.divide(1.0, paths, out=inverse, where=reachable & (paths > 0))
    components = list(nx.connected_components(graph))
    if graph.number_of_edges():
        communities = nx.community.greedy_modularity_communities(graph, weight="weight")
        modularity = float(nx.community.modularity(graph, communities, weight="weight"))
        clustering = float(nx.average_clustering(graph, weight="weight"))
    else:
        modularity, clustering = 0.0, 0.0
    return {
        "efficiency": float(inverse.sum() / (n * (n - 1))),
        "density": float(nx.density(graph)), "clustering": clustering,
        "modularity": modularity, "components": len(components),
        "largest_component_fraction": max(map(len, components)) / n,
        # Characteristic path length of the full graph is undefined if disconnected.
        "path_length": float(paths[off_diagonal].mean()) if len(components) == 1 else None,
        "reachable_path_length": float(paths[reachable].mean()) if reachable.any() else None,
        "edge_count": graph.number_of_edges(),
        "total_weight": float(weights.sum() / 2), "node_count": n,
    }


def node_metrics(matrix) -> list[dict]:
    weights = validate_matrix(matrix)
    strengths = weights.sum(axis=1)
    cutoff = float(strengths.mean() + strengths.std())
    graph = nx.from_numpy_array(weights)
    for _, _, data in graph.edges(data=True):
        data["distance"] = 1.0 / data["weight"]
    betweenness = nx.betweenness_centrality(graph, weight="distance", normalized=True)
    closeness = nx.closeness_centrality(graph, distance="distance", wf_improved=True)
    if graph.number_of_edges():
        communities = list(nx.community.greedy_modularity_communities(graph, weight="weight"))
        try:
            eigenvector = nx.eigenvector_centrality(graph, weight="weight", max_iter=1000, tol=1e-8)
        except nx.PowerIterationFailedConvergence:
            eigenvector = {index: None for index in graph}
    else:
        communities = [set(graph)]
        eigenvector = {index: 0.0 for index in graph}
    participation = np.zeros(len(weights))
    for community in communities:
        community_strength = weights[:, sorted(community)].sum(axis=1)
        share = np.divide(community_strength, strengths, out=np.zeros_like(strengths), where=strengths > 0)
        participation += share**2
    participation = np.where(strengths > 0, np.maximum(0, 1 - participation), 0)
    return [
        {"strength": float(strength), "degree": int(np.count_nonzero(weights[i])),
         "is_hub": bool(strength > cutoff and strength > 0),
         "betweenness": float(betweenness[i]), "closeness": float(closeness[i]),
         "eigenvector": eigenvector[i], "participation_coefficient": float(participation[i])}
        for i, strength in enumerate(strengths)
    ]
