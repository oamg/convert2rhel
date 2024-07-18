import sys


project = "convert2rhel"
copyright = "2024, Convert2RHEL Team"
author = "Convert2RHEL Team"

# -- Options for HTML output -------------------------------------------------
# Adapted from https://github.com/JamesALeedham/Sphinx-Autosummary-Recursion

extensions = [
    "sphinx.ext.autodoc",  # Core Sphinx library for auto html doc generation from docstrings
    "sphinx.ext.autosummary",  # Create neat summary tables for modules/classes/methods etc
    "sphinx.ext.intersphinx",  # Link to other project's documentation (see mapping below)
    #    'sphinx.ext.linkcode',  # Add a link to the Python source code for classes, functions etc.
    "sphinx_autodoc_typehints",  # Automatically document param types (less noise in class signature)
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}

# For external system related libraries that might be difficult to get on the system
# we can utilize auto mocking to make sure it works correctly
# See https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#confval-autodoc_mock_imports
autodoc_mock_imports = ["dnf", "yum", "rpm", "hawkey", "dbus", "pexpect"]
autosummary_generate = True  # Turn on sphinx.ext.autosummary
autoclass_content = "both"  # Add __init__ doc (ie. params) to class summaries
html_show_sourcelink = False  # Remove 'view source code' from top of page (for html, not python)
autodoc_inherit_docstrings = True  # If no docstring, inherit from base class
set_type_checking_flag = True  # Enable 'expensive' imports for sphinx_autodoc_typehints
add_module_names = False  # Remove namespaces from class/method signatures
modindex_common_prefix = ["convert2rhel."]

default_role = "code"

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

exclude_patterns = []

sys.path.append("../")

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pyramid"
html_theme_options = {
    "sidebarwidth": "20%",
}
html_static_path = ["_static"]
