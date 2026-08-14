"""draftdiff — learn a writing voice from the edits made before hitting send.

The loop nobody closes: an agent writes a draft, a human rewrites part of it,
the human sends, and the agent writes the next one exactly the same way. This
package holds the two versions side by side, counts what changed across all of
them, and emits a block of style rules to paste back into the agent's prompt.

Nothing here sends, reads a mailbox, or touches the network.
"""

__version__ = "0.1.0"
