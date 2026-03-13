(function(global) {
    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function hasAllowedPrefix(href, prefixes) {
        var i;
        for (i = 0; i < prefixes.length; i += 1) {
            if (href.indexOf(prefixes[i]) === 0) {
                return true;
            }
        }
        return false;
    }

    function extractMarkdownToken(text, start, image) {
        var prefix = image ? '![' : '[';
        var labelStart;
        var labelEnd;
        var hrefStart;
        var hrefEnd;

        if (text.indexOf(prefix, start) !== start) {
            return null;
        }

        labelStart = start + prefix.length;
        labelEnd = text.indexOf(']', labelStart);
        if (labelEnd === -1 || labelEnd + 1 >= text.length) {
            return null;
        }
        if (text.charAt(labelEnd + 1) !== '(') {
            return null;
        }

        hrefStart = labelEnd + 2;
        hrefEnd = text.indexOf(')', hrefStart);
        if (hrefEnd === -1) {
            return null;
        }

        return {
            label: text.slice(labelStart, labelEnd).replace(/^\s+|\s+$/g, ''),
            href: text.slice(hrefStart, hrefEnd).replace(/^\s+|\s+$/g, ''),
            end: hrefEnd + 1
        };
    }

    function renderImage(label, href) {
        if (!hasAllowedPrefix(href, ['http://', 'https://', '/'])) {
            return escapeHtml(label);
        }
        return (
            '<img class="rich-text-image" src="' + escapeHtml(href) +
            '" alt="' + escapeHtml(label) + '">'
        );
    }

    function renderLink(label, href) {
        if (!hasAllowedPrefix(href, ['http://', 'https://', 'mailto:', '/'])) {
            return escapeHtml(label);
        }
        return (
            '<a href="' + escapeHtml(href) + '">' +
            escapeHtml(label) +
            '</a>'
        );
    }

    function renderInline(text) {
        var output = [];
        var cursor = 0;
        var nextBang;
        var nextBracket;
        var nextPos;
        var token;

        text = String(text || '');

        while (cursor < text.length) {
            nextBang = text.indexOf('!', cursor);
            nextBracket = text.indexOf('[', cursor);
            if (nextBang === -1) {
                nextPos = nextBracket;
            } else if (nextBracket === -1) {
                nextPos = nextBang;
            } else {
                nextPos = Math.min(nextBang, nextBracket);
            }

            if (nextPos === -1) {
                output.push(escapeHtml(text.slice(cursor)));
                break;
            }
            if (nextPos > cursor) {
                output.push(escapeHtml(text.slice(cursor, nextPos)));
                cursor = nextPos;
            }

            token = extractMarkdownToken(text, cursor, true);
            if (token) {
                output.push(renderImage(token.label, token.href));
                cursor = token.end;
                continue;
            }

            token = extractMarkdownToken(text, cursor, false);
            if (token) {
                output.push(renderLink(token.label, token.href));
                cursor = token.end;
                continue;
            }

            output.push(escapeHtml(text.charAt(cursor)));
            cursor += 1;
        }

        return output.join('');
    }

    function renderStandaloneImage(line) {
        var token = extractMarkdownToken(line, 0, true);
        if (!token || token.end !== line.length) {
            return null;
        }
        if (!hasAllowedPrefix(token.href, ['http://', 'https://', '/'])) {
            return null;
        }
        return '<figure class="rich-text-figure">' +
            renderImage(token.label, token.href) +
            '</figure>';
    }

    function renderRichText(text) {
        var lines = String(text || '').split(/\r?\n/);
        var output = [];
        var paragraph = [];
        var bullets = [];
        var i;
        var line;
        var trimmed;
        var imageHtml;

        function flushParagraph() {
            if (!paragraph.length) {
                return;
            }
            output.push('<p>' + paragraph.join('<br>') + '</p>');
            paragraph = [];
        }

        function flushBullets() {
            var items = [];
            if (!bullets.length) {
                return;
            }
            for (i = 0; i < bullets.length; i += 1) {
                items.push('<li>' + renderInline(bullets[i]) + '</li>');
            }
            output.push('<ul class="rich-text-list">' + items.join('') + '</ul>');
            bullets = [];
        }

        for (i = 0; i < lines.length; i += 1) {
            line = lines[i].replace(/\s+$/g, '');
            trimmed = line.replace(/^\s+|\s+$/g, '');

            if (!trimmed) {
                flushParagraph();
                flushBullets();
                continue;
            }

            imageHtml = renderStandaloneImage(trimmed);
            if (imageHtml) {
                flushParagraph();
                flushBullets();
                output.push(imageHtml);
                continue;
            }

            if (trimmed.indexOf('- ') === 0) {
                flushParagraph();
                bullets.push(trimmed.slice(2).replace(/^\s+|\s+$/g, ''));
                continue;
            }

            flushBullets();
            paragraph.push(renderInline(line));
        }

        flushParagraph();
        flushBullets();

        return output.join('');
    }

    function insertTemplate(textarea, template) {
        var value = textarea.value || '';
        var start = textarea.selectionStart || 0;
        var end = textarea.selectionEnd || 0;
        textarea.value = value.slice(0, start) + template + value.slice(end);
        textarea.selectionStart = start + template.length;
        textarea.selectionEnd = start + template.length;
        textarea.focus();
    }

    function bindBlock(block) {
        var textarea = block.querySelector('[data-rich-text-role="source"]');
        var preview = block.querySelector('[data-rich-text-role="preview"]');
        var buttons;
        var i;

        if (!textarea || !preview) {
            return;
        }

        function refreshPreview() {
            var html = renderRichText(textarea.value);
            preview.innerHTML = html || '<p class="help-caption">Preview updates as you type.</p>';
        }

        textarea.addEventListener('input', refreshPreview);
        refreshPreview();

        buttons = block.querySelectorAll('.rich-text-insert');
        for (i = 0; i < buttons.length; i += 1) {
            buttons[i].addEventListener('click', function() {
                insertTemplate(textarea, this.getAttribute('data-insert-template') || '');
                refreshPreview();
            });
        }
    }

    function init(root) {
        var blocks = (root || document).querySelectorAll('[data-help-block]');
        var i;
        for (i = 0; i < blocks.length; i += 1) {
            bindBlock(blocks[i]);
        }
    }

    global.DJ4XOLRichTextEditor = {
        init: init,
        renderRichText: renderRichText
    };
})(window);
