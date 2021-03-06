"""
Filtering algorithms expect data to come in the form of Template, World
objects.
"""

from .misc import index_map
import matplotlib.pyplot as plt
import scipy.sparse as sparse
import numpy as np
import networkx as nx
import pandas as pd
import functools
import time

# TODO: get rid of _GraphWithCandidates and filter related data stuff
# TODO: bring back functions needed for neighborhood filter

class _Graph:
    def __init__(self, nodes, channels, adjs):
        self.ch_to_adj = {ch: adj for ch, adj in zip(channels, adjs)}
        self.nodes = np.array(nodes)
        self.n_nodes = len(nodes)
        self.node_idxs = index_map(nodes)

        self._composite_adj = None
        self._sym_composite_adj = None
        self._is_nbr = None

    @property
    def composite_adj(self):
        if self._composite_adj is None:
            self._composite_adj = sum(self.ch_to_adj.values())

        return self._composite_adj

    @property
    def sym_composite_adj(self):
        if self._sym_composite_adj is None:
            self._sym_composite_adj = self.composite_adj + self.composite_adj.T

        return self._sym_composite_adj

    @property
    def is_nbr(self):
        if self._is_nbr is None:
            self._is_nbr = self.sym_composite_adj > 0

        return self._is_nbr

    @property
    def channels(self):
        return self.ch_to_adj.keys()

    @property
    def adjs(self):
        return self.ch_to_adj.values()

    @property
    def nbr_idx_pairs(self):
        """
        Returns a 2d array with 2 columns. Each row contains the node idxs of
        a pair of neighbors in the graph. Each pair is only returned once, so
        for example only one of (0,3) and (3,0) could appear as rows.
        """
        return np.argwhere(sparse.tril(self.is_nbr))

    def subgraph(self, node_idxs):
        """
        Returns the subgraph induced by candidates
        """

        # throw out nodes not belonging to the desired subgraph
        nodes = self.nodes[node_idxs]
        adjs = [adj[node_idxs, :][:, node_idxs] for adj in self.adjs]

        # Return a new graph object for the induced subgraph
        return self.__class__(subgraph_nodes, self.channels, adjs)

    def copy(self):
        """
        The only thing this bothers to copy is the adjacency matrices
        """
        return self.__class__(
            self.nodes, self.channels, [adj.copy() for adj in self.adjs])


class _GraphWithCandidates(_Graph):
    # TODO: add flag to indicate whether any node has any candidates

    def __init__(self, candidates, nodes, channels, adjs, is_cand=None):
        super().__init__(nodes, channels, adjs)

        # Typically these correspond to the nodes of another graph
        self.cands = np.array(candidates)
        self.n_cands = len(candidates)
        self.cand_idxs = index_map(candidates)

        if is_cand is None:
            is_cand = np.ones((len(nodes), len(candidates)), dtype=np.bool_)

        # self.is_cand[i,j] takes value 1 if self.cands[j] is a candidate for
        # self.nodes[i] and takes value 0 otherwise
        self.is_cand = is_cand

    def get_cands(self, node):
        """
        Returns a 1d array of the current candidates for `node`
        """
        node_idx = self.node_idxs[node]
        return self.cands[self.is_cand[node_idx]]

    # TODO: use this function anywhere it is currently being calculated manually
    def get_cand_counts(self):
        """
        Returns a 1d array of the number of candidates for each node
        """
        return self.is_cand.sum(axis=1)

    def summarize(self):
        # Nodes that have only one candidate
        identified = [node for node in self.nodes
                      if len(self.get_cands(node))==1]
        n_found = len(identified)

        # Assuming ground truth nodes have same names, get the nodes for which
        # ground truth identity is not a candidate
        missing_ground_truth = [node for node in self.nodes
                                if node not in self.get_cands(node)]
        n_missing = len(missing_ground_truth)

        # Use number of candidates to decide the order to print the summaries
        cand_counts = np.sum(self.is_cand, axis=1)
        def key_func(node, cand_counts=cand_counts):
            return (-cand_counts[self.node_idxs[node]], -self.node_idxs[node])

        # TODO: if multiple nodes have the same candidates, condense them
        for node in sorted(self.nodes, key=key_func):
            cands = self.get_cands(node)
            n_cands = len(cands)

            # TODO: abstract out the getting and setting before and after
            print_opts = np.get_printoptions()
            np.set_printoptions(threshold=10, edgeitems=6)
            print(node, "has", n_cands, "candidates:", cands)
            np.set_printoptions(**print_opts)

        if n_found:
            print(n_found, "template nodes have 1 candidate:", identified)

        # This message is useful for debugging datasets for which you have
        # a ground truth signal
        if n_missing:
            print(n_missing, "nodes are missing ground truth candidate:",
                  missing_ground_truth)

    def copy(self):
        """
        The only things we bother copying are the is_cand matrix and the
        adjacency matrices. Everything else gets passed by reference.
        """
        return self.__class__(self.cands, self.nodes, self.channels,
                              [adj.copy() for adj in self.adjs],
                              is_cand=self.is_cand.copy())


    # TODO: clean up
    def plot(self, labels="candidate_counts"):

        if not self._nxgraph:
            self._nxgraph = nx.from_scipy_sparse_matrix(self.composite_adj,
                                           create_using=nx.DiGraph())

            self._pos = {}

            subgraphs = list(nx.weakly_connected_component_subgraphs(self._nxgraph))

            for subfig_i, subgraph in enumerate(subgraphs):
                df = pd.DataFrame(index=self._nxgraph.nodes(),
                         columns=self._nxgraph.nodes())
                for row, data in nx.shortest_path_length(subgraph.to_undirected()):
                    for col, dist in data.items():
                        df.loc[row,col] = dist
                        pos = nx.kamada_kawai_layout(subgraph, dist=df.to_dict())

                        subfig_center = np.array([2.5*subfig_i, 0])
                        pos = {key: subfig_center + val for key, val in pos.items()}

                        self._pos.update(pos)

        if labels == "candidate_counts":
            labels = {i: len(self.get_candidate_set(node))
                      for i, node in enumerate(self.nodes)}
        else:
            labels = {i: node for i, node in enumerate(self.nodes)}

        nx.draw(self._nxgraph,
                node_size=1000,
                edge_color="black",
                node_color="#26FEFD",
                labels=labels,
                pos=self._pos)

class World(_Graph): pass
class Template(_GraphWithCandidates): pass
