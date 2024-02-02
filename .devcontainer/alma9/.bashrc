#!/usr/bin/bash

alias python='python3'
alias ll='ls -lh'
alias la='ls -lah'
alias cd..='cd ..'
alias rm='rm -I'

# set a fancy prompt (non-color, unless we know we "want" color)
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac
PS1='\[\033[01;34m\]\u\[\033[38;5;124m\](container)\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
unset color_prompt force_color_prompt
