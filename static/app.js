// Email Server JavaScript Functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize form validation
    initializeFormValidation();
    
    // Initialize auto-save for compose form
    initializeAutoSave();
    
    // Initialize email list interactions
    initializeEmailList();
    
    // Initialize keyboard shortcuts
    initializeKeyboardShortcuts();
});

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[title]'));
    tooltipTriggerList.forEach(function(tooltipTriggerEl) {
        if (window.bootstrap && window.bootstrap.Tooltip) {
            new bootstrap.Tooltip(tooltipTriggerEl);
        }
    });
}

// Form validation and enhancement
function initializeFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        // Add custom validation styling
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                
                // Highlight first invalid field
                const firstInvalid = form.querySelector(':invalid');
                if (firstInvalid) {
                    firstInvalid.focus();
                    showNotification('Please fill in all required fields', 'error');
                }
            }
            
            form.classList.add('was-validated');
        });
        
        // Real-time email validation
        const emailInputs = form.querySelectorAll('input[type="email"]');
        emailInputs.forEach(input => {
            input.addEventListener('blur', function() {
                validateEmailField(input);
            });
        });
    });
}

// Email field validation
function validateEmailField(input) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const isValid = emailRegex.test(input.value);
    
    if (input.value && !isValid) {
        input.classList.add('is-invalid');
        showFieldError(input, 'Please enter a valid email address');
    } else {
        input.classList.remove('is-invalid');
        hideFieldError(input);
    }
}

// Show field error
function showFieldError(input, message) {
    hideFieldError(input); // Remove existing error first
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    
    input.parentNode.appendChild(errorDiv);
}

// Hide field error
function hideFieldError(input) {
    const existingError = input.parentNode.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.remove();
    }
}

// Auto-save functionality for compose form
function initializeAutoSave() {
    const composeForm = document.getElementById('composeForm');
    if (!composeForm) return;
    
    let autoSaveTimer;
    const autoSaveInterval = 120000; // 2 minutes
    
    function autoSave() {
        const formData = new FormData(composeForm);
        const hasContent = formData.get('subject') || formData.get('body_text') || formData.get('body_html');
        
        if (hasContent) {
            formData.append('save_draft', '1');
            
            fetch(composeForm.action, {
                method: 'POST',
                body: formData
            }).then(response => {
                if (response.ok) {
                    showNotification('Draft auto-saved', 'info', 2000);
                }
            }).catch(error => {
                console.error('Auto-save failed:', error);
            });
        }
    }
    
    // Start auto-save timer
    function startAutoSave() {
        clearInterval(autoSaveTimer);
        autoSaveTimer = setInterval(autoSave, autoSaveInterval);
    }
    
    // Monitor form changes
    const formInputs = composeForm.querySelectorAll('input, textarea, select');
    formInputs.forEach(input => {
        input.addEventListener('input', startAutoSave);
    });
    
    // Save on page unload
    window.addEventListener('beforeunload', function(event) {
        const formData = new FormData(composeForm);
        const hasUnsavedContent = formData.get('subject') || formData.get('body_text') || formData.get('body_html');
        
        if (hasUnsavedContent) {
            event.preventDefault();
            event.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            return event.returnValue;
        }
    });
}

// Email list interactions
function initializeEmailList() {
    // Row click handling for email list
    const emailRows = document.querySelectorAll('.email-row');
    emailRows.forEach(row => {
        row.addEventListener('click', function(event) {
            // Don't navigate if clicking on buttons or checkboxes
            if (event.target.closest('.btn') || event.target.closest('.form-check-input')) {
                return;
            }
            
            const emailId = row.dataset.emailId;
            if (emailId) {
                window.location.href = `/email/${emailId}`;
            }
        });
    });
    
    // Bulk actions
    const selectAllCheckbox = document.getElementById('selectAllCheck');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const emailCheckboxes = document.querySelectorAll('.email-checkbox');
            emailCheckboxes.forEach(checkbox => {
                checkbox.checked = selectAllCheckbox.checked;
            });
            updateBulkActions();
        });
    }
    
    // Individual checkbox changes
    const emailCheckboxes = document.querySelectorAll('.email-checkbox');
    emailCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', updateBulkActions);
    });
}

// Update bulk action buttons
function updateBulkActions() {
    const checkedBoxes = document.querySelectorAll('.email-checkbox:checked');
    const deleteBtn = document.getElementById('deleteBtn');
    const selectAllCheck = document.getElementById('selectAllCheck');
    
    if (deleteBtn) {
        deleteBtn.disabled = checkedBoxes.length === 0;
        if (checkedBoxes.length > 0) {
            deleteBtn.innerHTML = `<i data-feather="trash-2" class="me-1"></i> Delete Selected (${checkedBoxes.length})`;
        } else {
            deleteBtn.innerHTML = '<i data-feather="trash-2" class="me-1"></i> Delete Selected';
        }
        
        // Re-initialize feather icons
        if (window.feather) {
            feather.replace();
        }
    }
    
    // Update select all checkbox state
    if (selectAllCheck) {
        const allCheckboxes = document.querySelectorAll('.email-checkbox');
        const allChecked = allCheckboxes.length > 0 && checkedBoxes.length === allCheckboxes.length;
        const someChecked = checkedBoxes.length > 0;
        
        selectAllCheck.checked = allChecked;
        selectAllCheck.indeterminate = someChecked && !allChecked;
    }
}

// Keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(event) {
        // Ctrl/Cmd + Enter to send email in compose form
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            const composeForm = document.getElementById('composeForm');
            if (composeForm) {
                event.preventDefault();
                composeForm.submit();
            }
        }
        
        // Ctrl/Cmd + S to save draft
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
            const composeForm = document.getElementById('composeForm');
            if (composeForm) {
                event.preventDefault();
                const formData = new FormData(composeForm);
                formData.append('save_draft', '1');
                
                fetch(composeForm.action, {
                    method: 'POST',
                    body: formData
                }).then(response => {
                    if (response.ok) {
                        showNotification('Draft saved', 'success');
                    } else {
                        showNotification('Failed to save draft', 'error');
                    }
                });
            }
        }
        
        // R for reply (in email detail view)
        if (event.key === 'r' && !event.ctrlKey && !event.metaKey) {
            const replyBtn = document.querySelector('a[href*="reply_to"]');
            if (replyBtn && !isTyping(event.target)) {
                event.preventDefault();
                window.location.href = replyBtn.href;
            }
        }
        
        // Delete key for delete email
        if (event.key === 'Delete' && !isTyping(event.target)) {
            const deleteBtn = document.querySelector('form[action*="/delete"] button[type="submit"]');
            if (deleteBtn) {
                event.preventDefault();
                if (confirm('Are you sure you want to delete this email?')) {
                    deleteBtn.click();
                }
            }
        }
    });
}

// Check if user is typing in an input field
function isTyping(element) {
    return ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName) ||
           element.contentEditable === 'true';
}

// Notification system
function showNotification(message, type = 'info', duration = 5000) {
    const alertClass = type === 'error' ? 'alert-danger' : 
                      type === 'success' ? 'alert-success' : 
                      type === 'warning' ? 'alert-warning' : 'alert-info';
    
    const iconName = type === 'error' ? 'alert-circle' : 
                    type === 'success' ? 'check-circle' : 
                    type === 'warning' ? 'alert-triangle' : 'info';
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    
    alertDiv.innerHTML = `
        <i data-feather="${iconName}" class="me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // Initialize feather icons for the new alert
    if (window.feather) {
        feather.replace();
    }
    
    // Auto-remove after duration
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, duration);
}

// Email format toggle in compose form
function toggleEmailFormat(format) {
    const textDiv = document.getElementById('textBodyDiv');
    const htmlDiv = document.getElementById('htmlBodyDiv');
    
    if (format === 'html') {
        textDiv.style.display = 'none';
        htmlDiv.style.display = 'block';
    } else {
        textDiv.style.display = 'block';
        htmlDiv.style.display = 'none';
    }
    
    // Update preview if available
    if (typeof updatePreview === 'function') {
        updatePreview();
    }
}

// Email search functionality
function initializeEmailSearch() {
    const searchInput = document.getElementById('emailSearch');
    if (!searchInput) return;
    
    let searchTimeout;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            const searchTerm = searchInput.value.toLowerCase();
            const emailRows = document.querySelectorAll('.email-row');
            
            emailRows.forEach(row => {
                const text = row.textContent.toLowerCase();
                const matches = text.includes(searchTerm);
                row.style.display = matches ? '' : 'none';
            });
        }, 300);
    });
}

// Copy text to clipboard
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            showNotification('Copied to clipboard', 'success', 2000);
        }).catch(err => {
            console.error('Failed to copy text: ', err);
            showNotification('Failed to copy text', 'error');
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            document.execCommand('copy');
            showNotification('Copied to clipboard', 'success', 2000);
        } catch (err) {
            console.error('Fallback: Oops, unable to copy', err);
            showNotification('Failed to copy text', 'error');
        }
        
        document.body.removeChild(textArea);
    }
}

// Email status checker
function checkEmailStatus() {
    fetch('/api/emails/status')
        .then(response => response.json())
        .then(data => {
            if (data.pending_emails > 0) {
                showNotification(`${data.pending_emails} email(s) pending`, 'info', 3000);
            }
        })
        .catch(error => {
            console.error('Error checking email status:', error);
        });
}

// Check email status on page load and periodically
document.addEventListener('DOMContentLoaded', function() {
    checkEmailStatus();
    
    // Check every 5 minutes
    setInterval(checkEmailStatus, 300000);
});

// Smooth scroll to top
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

// Add scroll to top button
function addScrollToTopButton() {
    const button = document.createElement('button');
    button.innerHTML = '<i data-feather="arrow-up"></i>';
    button.className = 'btn btn-primary position-fixed';
    button.style.cssText = 'bottom: 20px; right: 20px; z-index: 9999; border-radius: 50%; width: 50px; height: 50px; display: none;';
    button.onclick = scrollToTop;
    
    document.body.appendChild(button);
    
    // Show/hide button based on scroll position
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 300) {
            button.style.display = 'block';
        } else {
            button.style.display = 'none';
        }
    });
    
    // Initialize feather icons
    if (window.feather) {
        feather.replace();
    }
}

// Initialize scroll to top button
document.addEventListener('DOMContentLoaded', addScrollToTopButton);

// Export functions for global use
window.EmailServer = {
    showNotification,
    copyToClipboard,
    toggleEmailFormat,
    scrollToTop,
    checkEmailStatus
};
