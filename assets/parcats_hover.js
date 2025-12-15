/**
 * Enhanced hover for Parcats charts
 * - Replaces placeholder percentages with computed values
 * - Adds CPT code explanations below codes in tooltips
 * - Resizes tooltip box after text modifications
 */

// CPT code explanations for actual billed codes
const ACTUAL_CODE_EXPLANATIONS = {
    "77402": "IMRT (Simple)",
    "G6003": "IMRT (Simple)",
    "G6004": "IMRT (Simple)",
    "G6005": "IMRT (Simple)",
    "G6006": "IMRT (Simple)",
    "77407": "IMRT (Intermediate)",
    "G6007": "IMRT (Intermediate)",
    "G6008": "IMRT (Intermediate)",
    "G6009": "IMRT (Intermediate)",
    "G6010": "IMRT (Intermediate)",
    "77412": "IMRT (Complex)",
    "G6011": "IMRT (Complex)",
    "G6012": "IMRT (Complex)",
    "G6013": "IMRT (Complex)",
    "G6014": "IMRT (Complex)",
    "77385": "IMRT (Simple)",
    "77386": "IMRT (Complex)",
    "G6015": "IMRT (Simple)",
    "G6016": "IMRT (Complex)",
    "77014": "CBCT",
    "77387": "IGRT",
    "G6002": "IGRT",
    "77372": "SRS",
    "77373": "SBRT",
};

// Track processed elements
const processedElements = new WeakSet();
const processedPaths = new WeakSet();

document.addEventListener('DOMContentLoaded', function() {
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) {
                    enhanceHoverText(node);
                }
            });
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });
});

function enhanceHoverText(element) {
    const textElements = element.querySelectorAll ? element.querySelectorAll('tspan') : [];
    let modified = false;
    
    textElements.forEach(function(textEl) {
        if (processedElements.has(textEl)) return;
        
        const text = textEl.textContent || '';
        let wasModified = false;
        
        // 1. Replace percentage placeholders: "X of Y (---.--%)" -> "X of Y (Z%)"
        const percentPattern = /(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+\(---\.--?%\)/;
        const percentMatch = text.match(percentPattern);
        if (percentMatch) {
            const numerator = parseInt(percentMatch[1].replace(/,/g, ''));
            const denominator = parseInt(percentMatch[2].replace(/,/g, ''));
            if (denominator > 0) {
                const percentage = ((numerator / denominator) * 100).toFixed(1);
                textEl.textContent = text.replace(percentMatch[0], `${percentMatch[1]} of ${percentMatch[2]} (${percentage}%)`);
                wasModified = true;
            }
        }
        
        // 2. Add explanation for CPT codes (first bold line in tooltip)
        if (!wasModified) {
            const trimmedText = text.trim();
            const explanation = ACTUAL_CODE_EXPLANATIONS[trimmedText];
            if (explanation) {
                textEl.textContent = `${trimmedText} - ${explanation}`;
                wasModified = true;
            }
        }
        
        if (wasModified) {
            processedElements.add(textEl);
            modified = true;
        }
    });
    
    // After modifying text, resize the tooltip background
    if (modified) {
        requestAnimationFrame(function() {
            resizeTooltipBox(element);
        });
    }
}

function resizeTooltipBox(element) {
    // Find hovertext groups
    const hoverGroups = element.classList && element.classList.contains('hovertext') 
        ? [element] 
        : (element.querySelectorAll ? element.querySelectorAll('.hovertext') : []);
    
    hoverGroups.forEach(function(group) {
        const path = group.querySelector('path');
        const textEl = group.querySelector('text');
        
        if (!path || !textEl || processedPaths.has(path)) return;
        
        try {
            // Get the text bounding box
            const textBBox = textEl.getBBox();
            // Get the path bounding box  
            const pathBBox = path.getBBox();
            
            // Calculate how much wider the text is than the path
            const extraWidth = Math.max(0, (textBBox.width + 20) - pathBBox.width);
            
            if (extraWidth > 5) {
                // Need to widen the path
                const d = path.getAttribute('d');
                if (d) {
                    // Simple approach: scale the path horizontally
                    const currentTransform = path.getAttribute('transform') || '';
                    // Apply a small scale to widen
                    const scale = (pathBBox.width + extraWidth) / pathBBox.width;
                    path.setAttribute('transform', currentTransform + ` scale(${scale}, 1)`);
                    processedPaths.add(path);
                }
            }
        } catch (e) {
            // getBBox can fail if element not rendered
        }
    });
}
