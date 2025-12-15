/**
 * Enhanced hover for Parcats charts
 * - Replaces placeholder percentages with computed values
 * - Adds CPT code explanations below codes in tooltips
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
    
    textElements.forEach(function(textEl) {
        if (processedElements.has(textEl)) return;
        
        const text = textEl.textContent || '';
        let modified = false;
        
        // 1. Replace percentage placeholders: "X of Y (---.--%)" -> "X of Y (Z%)"
        const percentPattern = /(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+\(---\.--?%\)/;
        const percentMatch = text.match(percentPattern);
        if (percentMatch) {
            const numerator = parseInt(percentMatch[1].replace(/,/g, ''));
            const denominator = parseInt(percentMatch[2].replace(/,/g, ''));
            if (denominator > 0) {
                const percentage = ((numerator / denominator) * 100).toFixed(1);
                textEl.textContent = text.replace(percentMatch[0], `${percentMatch[1]} of ${percentMatch[2]} (${percentage}%)`);
                modified = true;
            }
        }
        
        // 2. Add explanation for CPT codes (first bold line in tooltip)
        // Look for codes that match our dictionary and are standalone (the category line)
        if (!modified) {
            const trimmedText = text.trim();
            const explanation = ACTUAL_CODE_EXPLANATIONS[trimmedText];
            if (explanation) {
                // This is a CPT code - add explanation
                textEl.textContent = `${trimmedText} - ${explanation}`;
                modified = true;
            }
        }
        
        if (modified) {
            processedElements.add(textEl);
        }
    });
}
