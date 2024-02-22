Documentation How-To
====================

The documentation has two inputs: docstrings in Python files of the
``./convert2rhel/`` module and plain ReST markup in ``.rst`` files in
``./docs/sources/*.rst``. Formatting rules for docstrings and rst
files may be slightly different.

Generally try to put information into docstrings including those at
the module-level.

Create additional rst files to describe generic concepts or anything
which doesn't fit into the scope of a specific module.

Layout
------

Rst files layout is currently very simple::

  index.rst
  -- all.rst          // Full API docs tree
  -- meta.rst         // Documentation about documentation
  -- actions.rst      // Dedicated page for a topic, can reference the API docs.

How to build
------------

With a standard Fedora environment you need to install dependencies::

  $ sudo dnf install python3-sphinx python3-sphinx-autodoc-typehints.noarchpython3-sphinx

And then got to `./docs/` and run make::

  $ make

The output is going to appear in `./docs/build/html`.

Tips & Tricks
--------------

References to modules, methods and classes
..........................................

To refer to a Python object use backticks.

It can be a little tricky due to use the correct name for the object. See the following examples::

   1. :mod:`actions`,     // works in docstrings, doesn't work in rst
   2. :class:`Action`,    // works in docstrings, doesn't work in rst
   3. :mod:`.actions`,    // looks fo all objects which end with the suffix `.actions`.
                          // As it finds two: convert2rhel.actions and convert2rhel.unit_tests.actions
                          // it takes the shortest of them
   4. :mod:`convert2rhel.actions`,  // fully-qualified name
   5. :mod:`~convert2rhel.unit_tests.actions`, // cuts the title to the last part
   6. :attr:`.Action.id`,
   7. :attr:`.Action.id`\ s, // see the note
   8. `.actions`. // text in backticks recognized as inline code by default.

Output:

1. :mod:`actions`,
2. :class:`Action`,
3. :mod:`.actions`,
4. :mod:`convert2rhel.actions`,
5. :mod:`~convert2rhel.unit_tests.actions`,
6. :attr:`.Action.id`,
7. :attr:`.Action.id`\ s,
8. `~convert2rhel.actions`.


.. note:: ReST recognizes a closing backtick only if it is followed by
   a space ot punctuation mark. If the backtick is followed by a
   letter, insert the escaped space "`\\ \ `" after it.
