// 页面加载完成后显示仪表盘
document.addEventListener('DOMContentLoaded', function() {
    showSection('dashboard');
    refreshDashboard();
});

// 切换页面部分
function showSection(sectionName, event) {
    // 隐藏所有部分
    document.querySelectorAll('.section').forEach(section => {
        section.style.display = 'none';
    });
    
    // 显示选中的部分
    document.getElementById(sectionName).style.display = 'block';
    
    // 更新导航项的激活状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('active');
    }

    // 如果是仪表盘部分，自动刷新数据
    if (sectionName === 'dashboard') {
        refreshDashboard();
    }
}

// 刷新仪表盘数据
function refreshDashboard() {
    // 显示加载状态
    const refreshBtn = document.getElementById('refresh-button');
    const icon = refreshBtn.querySelector('i');
    icon.classList.add('fa-spin');
    refreshBtn.disabled = true;

    fetch('/admin_dashboard')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                updateDashboardData(data);
            } else {
                showError('获取数据失败：' + data.message);
            }
        })
        .catch(error => {
            showError('获取数据失败：' + error.message);
        })
        .finally(() => {
            // 恢复按钮状态
            icon.classList.remove('fa-spin');
            refreshBtn.disabled = false;
        });
}

// 更新仪表盘数据
function updateDashboardData(data) {
    // 更新激活统计
    document.getElementById('total-activations').textContent = data.total_activations;
    document.getElementById('today-activations').textContent = data.today_activations;
    
    // 更新地址统计
    document.getElementById('total-addresses').textContent = data.total_addresses;
    document.getElementById('today-addresses').textContent = data.today_addresses;
    
    // 更新发货状态统计
    updateProgressBars('shipping-stats', data.shipping_stats, [
        { key: 'shipped', label: '已发货' },
        { key: 'pending', label: '待发货' },
        { key: 'cancelled', label: '已取消' }
    ]);
    
    // 更新金融卡类型分布
    updateProgressBars('card-type-stats', data.card_type_stats, [
        { key: 'platinum', label: '铂金卡' },
        { key: 'black', label: '黑金卡' },
        { key: 'supreme', label: '至尊卡' }
    ]);
}

// 更新进度条
function updateProgressBars(containerId, data, items) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // 计算最大值用于百分比计算
    const maxValue = Math.max(...Object.values(data));

    items.forEach(item => {
        const value = data[item.key] || 0;
        const percentage = maxValue > 0 ? (value / maxValue * 100) : 0;
        
        const barGroup = container.querySelector(`div.stat-bar-group:nth-child(${items.indexOf(item) + 1})`);
        if (barGroup) {
            const progressBar = barGroup.querySelector('.progress-bar');
            const valueSpan = barGroup.querySelector('.stat-value');
            
            // 使用动画更新进度条
            progressBar.style.transition = 'width 0.6s ease-out';
            progressBar.style.width = `${percentage}%`;
            
            // 更新数值
            valueSpan.textContent = value;
        }
    });
}

// 显示模态框
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
    }
}

// 隐藏模态框
function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// 显示错误消息
function showError(message, type = 'error') {
    const errorDiv = document.createElement('div');
    errorDiv.className = `error-message ${type}`;
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);

    // 5秒后自动移除
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}

// 搜索账户
function searchAccounts() {
    const phone = document.getElementById('account-search').value.trim();
    const level = document.getElementById('account-level-filter').value;
    const status = document.getElementById('activation-status-filter').value;
    
    const params = new URLSearchParams({
        phone,
        level,
        status
    });

    // 使用新的API端点
    fetch(`/api/admin/accounts/search_new?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log("获取到账户数据:", data.accounts);
                updateAccountList(data.accounts);
            } else {
                showError(data.message || '搜索失败');
            }
        })
        .catch(error => {
            console.error("搜索错误:", error);
            showError('搜索失败：' + error.message);
        });
}

// 修改API路径以匹配后端路由
function refreshShippingList() {
    fetch('/admin_get_shipping_records')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateShippingList(data.records);
            } else {
                showError(data.message || '获取发货列表失败');
            }
        })
        .catch(error => {
            showError('获取发货列表失败：' + error.message);
        });
}

function refreshAccountList() {
    const level = document.getElementById('account-level-filter').value;
    const status = document.getElementById('activation-status-filter').value;
    
    const params = new URLSearchParams({
        level,
        status
    });
    
    fetch(`/admin_get_accounts?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateAccountList(data.accounts);
            } else {
                showError(data.message || '获取账户列表失败');
            }
        })
        .catch(error => {
            showError('获取账户列表失败：' + error.message);
        });
}

function refreshCardList() {
    const status = document.getElementById('card-status-filter').value;
    
    const params = new URLSearchParams({
        status
    });
    
    fetch(`/admin_get_cards?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateCardList(data.cards);
            } else {
                showError(data.message || '获取金融卡列表失败');
            }
        })
        .catch(error => {
            showError('获取金融卡列表失败：' + error.message);
        });
}

// 修改添加账户函数
function submitAddAccount() {
    const phone = document.getElementById('add_account_phone').value.trim();
    const cardLevel = document.getElementById('add_account_card_level').value.trim();
    
    // 验证输入
    if (!phone) {
        showError('请输入手机号码');
        return;
    }
    if (!cardLevel) {
        showError('请选择金融卡等级');
        return;
    }

    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        showError('请输入有效的手机号码');
        return;
    }

    // 验证金融卡等级
    const validLevels = ['platinum', 'black', 'supreme'];
    if (!validLevels.includes(cardLevel)) {
        showError('请选择有效的金融卡等级');
        return;
    }

    // 打印请求数据，用于调试
    console.log('添加账户请求数据:', {
        phone: phone,
        card_level: cardLevel
    });
    
    fetch('/admin_add_account', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            phone: phone,
            card_level: cardLevel
        })
    })
    .then(response => response.json())
    .then(data => {
        // 打印响应数据，用于调试
        console.log('添加账户响应数据:', data);
        
        if (data.success) {
            showError('添加账户成功', 'success');
            hideModal('add_account_modal');
            // 重置表单
            document.getElementById('add_account_phone').value = '';
            document.getElementById('add_account_card_level').value = '';
            // 刷新账户列表
            refreshAccountList();
        } else {
            showError(data.message || '添加账户失败');
        }
    })
    .catch(error => {
        console.error('添加账户错误:', error);
        showError('添加账户失败：' + error.message);
    });
}

// 修改批量添加账户函数
function submitBatchAddAccounts() {
    const phones = document.getElementById('batch_add_accounts_phones').value
        .split('\n')
        .map(phone => phone.trim())
        .filter(phone => phone);
    const cardLevel = document.getElementById('batch_add_accounts_card_level').value.trim();
    
    // 验证输入
    if (!phones.length) {
        showError('请输入手机号码');
        return;
    }
    if (!cardLevel) {
        showError('请选择金融卡等级');
        return;
    }

    // 验证金融卡等级
    const validLevels = ['platinum', 'black', 'supreme'];
    if (!validLevels.includes(cardLevel)) {
        showError('请选择有效的金融卡等级');
        return;
    }

    // 验证手机号格式
    const invalidPhones = phones.filter(phone => !/^1[3-9]\d{9}$/.test(phone));
    if (invalidPhones.length > 0) {
        showError(`以下手机号格式无效：${invalidPhones.join(', ')}`);
        return;
    }
    
    fetch('/admin_batch_add_accounts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            accounts: phones.map(phone => ({
                phone: phone,
                card_level: cardLevel
            }))
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError(data.message, 'success');
            hideModal('batch_add_accounts_modal');
            // 重置表单
            document.getElementById('batch_add_accounts_phones').value = '';
            document.getElementById('batch_add_accounts_card_level').value = '';
            // 刷新账户列表
            refreshAccountList();
        } else {
            showError(data.message);
        }
    })
    .catch(error => {
        showError('批量添加账户失败：' + error.message);
    });
}

function editAccount(phone) {
    // 首先检查必要的DOM元素是否存在
    const phoneInput = document.getElementById('edit_account_phone');
    const cardLevelInput = document.getElementById('edit_account_card_level');
    
    if (!phoneInput || !cardLevelInput) {
        showError('编辑表单元素未找到，请检查页面结构');
        return;
    }

    fetch(`/admin_search?query=${encodeURIComponent(phone)}`)
        .then(response => response.json())
        .then(data => {
            if (data.成功 || data.success) {
                console.log('获取账户信息成功:', data);
                
                // 获取账户信息，可能在不同的属性路径下
                const accountInfo = data.result || 
                                   (data.结果 && data.结果.账户信息) || 
                                   {};
                
                // 安全地设置表单值
                try {
                    phoneInput.value = phone || '';
                    cardLevelInput.value = accountInfo.card_level || 'platinum';
                    
                    // 显示编辑模态框
                    showModal('edit_account_modal');
                } catch (error) {
                    console.error('设置表单值时出错:', error);
                    showError('设置表单值失败：' + error.message);
                }
            } else {
                showError(data.消息 || data.message || '获取账户信息失败');
            }
        })
        .catch(error => {
            console.error('获取账户信息错误:', error);
            showError('获取账户信息失败：' + error.message);
        });
}

function deleteAccount(phone) {
    if (!confirm('确定要删除该账户吗？')) {
        return;
    }

    fetch('/admin_delete_account', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ phone })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('删除成功', 'success');
            refreshAccountList();
        } else {
            showError(data.message || '删除失败');
        }
    })
    .catch(error => {
        showError('删除失败：' + error.message);
    });
}

// 执行查询
function performSearch() {
    const searchInput = document.getElementById('search-input').value.trim();
    if (!searchInput) {
        showError('请输入搜索内容');
        return;
    }

    // 显示加载状态
    const searchBtn = document.querySelector('.search-controls .primary-btn');
    if (searchBtn) {
        searchBtn.disabled = true;
        const originalHTML = searchBtn.innerHTML;
        searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 查询中...';
    }

    fetch(`/admin_search?query=${encodeURIComponent(searchInput)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // 打印返回数据，用于调试
            console.log('查询结果:', data);
            
            // 清空结果容器
            const tbody = document.getElementById('search-results-body');
            tbody.innerHTML = '';
            
            // 设置查询结果标题
            const resultHeader = document.getElementById('search-result-header');
            const queryText = document.getElementById('search-query-text');
            if (resultHeader && queryText) {
                queryText.textContent = searchInput;
                resultHeader.style.display = 'block';
            }
            
            if (data.success || data.成功) {
                const results = data.results || data.结果;
                
                if (results) {
                    // 更新账户信息表格
                    const accountInfo = results.账户信息 || results.account;
                    if (accountInfo) {
                        updateSingleSearchResult(accountInfo);
                    }
                    
                    // 显示详细登记信息
                    showDetailedResults(results);
                } else {
                    showError('未找到结果');
                }
            } else {
                showError(data.message || data.消息 || '查询失败');
            }
        })
        .catch(error => {
            console.error('查询错误:', error);
            showError('查询失败：' + error.message);
        })
        .finally(() => {
            // 恢复按钮状态
            const searchBtn = document.querySelector('.search-controls .primary-btn');
            if (searchBtn) {
                searchBtn.disabled = false;
                searchBtn.innerHTML = '<i class="fas fa-search"></i> 查询';
            }
        });
}

// 显示详细登记信息（激活登记和地址登记）
function showDetailedResults(results) {
    // 获取详细信息容器
    const detailsContainer = document.getElementById('search-details-container');
    const activationDetails = document.getElementById('activation-details');
    const addressDetails = document.getElementById('address-details');
    
    if (!detailsContainer || !activationDetails || !addressDetails) {
        console.error('找不到详细信息展示区域');
        return;
    }
    
    // 清空详细信息区域
    activationDetails.innerHTML = '';
    addressDetails.innerHTML = '';
    
    // 添加激活登记信息
    if (results.激活登记) {
        const activationTitle = document.createElement('h4');
        activationTitle.textContent = '激活登记信息';
        activationDetails.appendChild(activationTitle);
        
        const activationInfo = document.createElement('div');
        activationInfo.className = 'detail-card';
        
        const activation = results.激活登记;
        
        // 添加操作按钮（编辑和删除）
        const editButton = document.createElement('div');
        editButton.className = 'edit-actions';
        editButton.innerHTML = `
            <button class="edit-action-btn" onclick="editActivation(${activation.id})">
                <i class="fas fa-edit"></i> 编辑
            </button>
            <button class="delete-action-btn" onclick="deleteActivation(${activation.id}, '${activation.phone}')">
                <i class="fas fa-trash"></i> 删除
            </button>
        `;
        
        // 添加详细信息
        activationInfo.innerHTML = `
            <p><strong>手机号码:</strong> ${activation.phone || '-'}</p>
            <p><strong>姓名:</strong> ${activation.name || '-'}</p>
            <p><strong>身份证号:</strong> ${activation.id_number || '-'}</p>
            <p><strong>卡号:</strong> ${activation.card_number || '-'}</p>
            <p><strong>卡片类型:</strong> ${getCardLevelName(activation.card_type)}</p>
            <p><strong>提交时间:</strong> ${formatDate(activation.submit_time)}</p>
        `;
        
        // 将编辑按钮添加到详细信息卡片中
        activationInfo.appendChild(editButton);
        activationDetails.appendChild(activationInfo);
    } else {
        const noInfo = document.createElement('p');
        noInfo.textContent = '未找到激活登记信息';
        activationDetails.appendChild(noInfo);
    }
    
    // 添加地址登记信息
    if (results.地址登记) {
        const addressTitle = document.createElement('h4');
        addressTitle.textContent = '地址登记信息';
        addressDetails.appendChild(addressTitle);
        
        const addressInfo = document.createElement('div');
        addressInfo.className = 'detail-card';
        
        const address = results.地址登记;
        
        // 添加操作按钮（编辑和删除）
        const editButton = document.createElement('div');
        editButton.className = 'edit-actions';
        editButton.innerHTML = `
            <button class="edit-action-btn" onclick="editAddress(${address.id})">
                <i class="fas fa-edit"></i> 编辑
            </button>
            <button class="delete-action-btn" onclick="deleteAddress(${address.id}, '${address.phone}')">
                <i class="fas fa-trash"></i> 删除
            </button>
        `;
        
        // 添加详细信息
        addressInfo.innerHTML = `
            <p><strong>手机号码:</strong> ${address.phone || '-'}</p>
            <p><strong>姓名:</strong> ${address.name || '-'}</p>
            <p><strong>身份证号:</strong> ${address.id_number || '-'}</p>
            <p><strong>收货电话:</strong> ${address.delivery_phone || '-'}</p>
            <p><strong>收货地址:</strong> ${address.delivery_address || '-'}</p>
            <p><strong>卡片类型:</strong> ${getCardLevelName(address.card_type)}</p>
            <p><strong>发货状态:</strong> <span class="status-badge status-${address.shipping_status || 'pending'}">${getShippingStatusName(address.shipping_status || 'pending')}</span></p>
            <p><strong>提交时间:</strong> ${formatDate(address.submit_time)}</p>
        `;
        
        // 将编辑按钮添加到详细信息卡片中
        addressInfo.appendChild(editButton);
        addressDetails.appendChild(addressInfo);
    } else {
        const noInfo = document.createElement('p');
        noInfo.textContent = '未找到地址登记信息';
        addressDetails.appendChild(noInfo);
    }
    
    // 显示详细信息区域
    detailsContainer.style.display = 'block';
}

// 更新单一查询结果
function updateSingleSearchResult(result) {
    const tbody = document.getElementById('search-results-body');
    if (!tbody) return;
    
    // 清空现有结果
    tbody.innerHTML = '';

    // 如果没有结果，或者结果为空，显示提示信息
    if (!result) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="7" class="text-center">未找到账户信息</td>`;
        tbody.appendChild(tr);
        return;
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${result.phone || '-'}</td>
        <td>${result.name || '-'}</td>
        <td>${result.id_number || '-'}</td>
        <td><span class="card-level level-${(result.card_level || 'unknown').toLowerCase()}">${getCardLevelName(result.card_level)}</span></td>
        <td><span class="status-badge ${result.activated ? 'status-activated' : 'status-not-activated'}">
            ${result.activated ? '已激活' : '未激活'}
        </span></td>
        <td><span class="status-badge status-${result.shipping_status || 'pending'}">
            ${getShippingStatusName(result.shipping_status || 'pending')}
        </span></td>
        <td>
            <button class="operation-btn edit-btn" onclick="editAccount('${result.phone}')">
                <i class="fas fa-edit"></i>
            </button>
            <button class="operation-btn delete-btn" onclick="deleteAccount('${result.phone}')">
                <i class="fas fa-trash"></i>
            </button>
        </td>
    `;
    tbody.appendChild(tr);
}

// 批量更新发货状态
function batchUpdateShipping() {
    const selectedRows = document.querySelectorAll('#shipping-table input[type="checkbox"]:checked');
    if (!selectedRows.length) {
        showError('请选择要更新的记录');
        return;
    }

    const phones = Array.from(selectedRows).map(checkbox => checkbox.value);
    
    if (!confirm(`确定要将选中的 ${phones.length} 条记录状态改为已发货吗？`)) {
        return;
    }
    
    fetch('/update_shipping_status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            phones: phones,
            status: 'shipped'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('更新成功', 'success');
            refreshShippingList();
        } else {
            showError(data.message || '更新失败');
        }
    })
    .catch(error => {
        showError('更新失败：' + error.message);
    });
}

// 导入金融卡
function importCards() {
    const fileInput = document.getElementById('card-file');
    if (!fileInput.files.length) {
        showError('请选择要导入的文件');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    fetch('/admin_import_cards', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('导入成功');
            document.getElementById('card-file-name').textContent = '未选择文件';
            fileInput.value = '';
            refreshCardList();
        } else {
            showError(data.message || '导入失败');
        }
    })
    .catch(error => {
        showError('导入失败：' + error.message);
    });
}

// 导出账户数据
function exportAccounts() {
    const level = document.getElementById('export-account-level').value;
    const status = document.getElementById('export-account-status').value;
    const startDate = document.getElementById('export-account-start-date').value;
    const endDate = document.getElementById('export-account-end-date').value;

    const params = new URLSearchParams({
        level,
        status,
        start_date: startDate,
        end_date: endDate
    });

    window.location.href = `/admin_export_accounts?${params.toString()}`;
}

// 获取发货状态名称
function getShippingStatusName(status) {
    if (!status || typeof status !== 'string') {
        return '未知';
    }
    const statusMap = {
        'pending': '待发货',
        'shipped': '已发货',
        'cancelled': '已取消'
    };
    return statusMap[status] || status || '未知';
}

// 更新发货列表
function updateShippingList(list) {
    const tbody = document.getElementById('shipping-list-body');
    tbody.innerHTML = '';

    if (!list || list.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="8" class="text-center">暂无发货记录</td>`;
        tbody.appendChild(tr);
        return;
    }

    list.forEach(item => {
        const tr = document.createElement('tr');
        // 兼容 card_type 和 card_level 字段名，确保不是 null 或 undefined
        const cardLevel = (item.card_type || item.card_level || 'unknown');
        const receiverName = item.receiver_name || item.name || '-';
        const address = item.address || item.delivery_address || '-';
        const status = item.status || item.shipping_status || 'pending';
        const trackingNumber = item.tracking_number || '';
        
        tr.innerHTML = `
            <td><input type="checkbox" value="${item.phone || ''}"></td>
            <td>${item.phone || '-'}</td>
            <td>${receiverName}</td>
            <td>${address}</td>
            <td>${getCardLevelName(cardLevel)}</td>
            <td><span class="status-badge status-${status}">
                ${getShippingStatusName(status)}
            </span></td>
            <td>
                <input type="text" class="tracking-input" value="${trackingNumber}"
                    onchange="updateTrackingNumber('${item.phone || ''}', this.value)"
                    ${status === 'cancelled' ? 'disabled' : ''}>
            </td>
            <td>
                <button class="operation-btn edit-btn" onclick="editShipping('${item.phone || ''}')">
                    <i class="fas fa-edit"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// 获取金融卡等级名称
function getCardLevelName(level) {
    if (!level || typeof level !== 'string') {
        return '未知';
    }
    const levelMap = {
        'platinum': '铂金卡',
        'black': '黑金卡',
        'supreme': '至尊卡',
        'unknown': '未知'
    };
    return levelMap[level.toLowerCase()] || '未知';
}

// 修改账户列表更新函数
function updateAccountList(accounts) {
    const tbody = document.getElementById('account-list-body');
    tbody.innerHTML = '';

    if (!accounts || accounts.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="6" class="text-center">暂无账户记录</td>`;
        tbody.appendChild(tr);
        return;
    }

    accounts.forEach(account => {
        // 确保card_level存在，如果不存在则使用默认值
        const cardLevel = (account.card_level || 'unknown');
        // 确保 cardLevel 是字符串且不为空
        const safeCardLevel = (typeof cardLevel === 'string' && cardLevel) ? cardLevel.toLowerCase() : 'unknown';
        // 检查激活状态，兼容旧版字段名
        const isActivated = account.is_activated !== undefined ? account.is_activated : account.activated;
        // 兼容不同的时间字段名称
        const createTime = account.registration_time || account.create_time || '-';
        const lastUpdated = account.last_updated || '-';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${account.phone || '-'}</td>
            <td><span class="card-level level-${safeCardLevel}">${getCardLevelName(cardLevel)}</span></td>
            <td><span class="status-badge ${isActivated ? 'status-activated' : 'status-not-activated'}">
                ${isActivated ? '已激活' : '未激活'}
            </span></td>
            <td>${formatDate(createTime)}</td>
            <td>${formatDate(lastUpdated)}</td>
            <td>
                <button class="operation-btn edit-btn" onclick="editAccount('${account.phone || ''}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="operation-btn delete-btn" onclick="deleteAccount('${account.phone || ''}')">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// 更新金融卡列表
function updateCardList(cards) {
    const tbody = document.getElementById('card-list-body');
    tbody.innerHTML = '';

    cards.forEach(card => {
        const tr = document.createElement('tr');
        // 安全地处理 status，避免 undefined 或 null
        const status = card.status || 'unknown';
        const safeStatus = (typeof status === 'string' && status) ? status.toLowerCase() : 'unknown';
        
        tr.innerHTML = `
            <td>${card.card_number || card.number || '-'}</td>
            <td><span class="status-${safeStatus}">${getCardStatusName(status)}</span></td>
            <td>${card.bound_phone || '-'}</td>
            <td>${card.activated_at ? formatDate(card.activated_at) : '-'}</td>
            <td>
                <button class="operation-btn edit-btn" onclick="editCard('${card.card_number || card.number || ''}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="operation-btn delete-btn" onclick="deleteCard('${card.card_number || card.number || ''}')">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// 格式化日期
function formatDate(dateString) {
    if (!dateString) return '-';
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) {
            return dateString; // 如果转换失败，返回原始字符串
        }
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        }).replace(/\//g, '-');
    } catch (e) {
        console.error('日期格式化错误:', e);
        return dateString;
    }
}

// 获取金融卡状态名称
function getCardStatusName(status) {
    if (!status || typeof status !== 'string') {
        return '未知';
    }
    const statusMap = {
        'available': '可用',
        'used': '已使用',
        'locked': '已锁定'
    };
    return statusMap[status.toLowerCase()] || status || '未知';
}

// 编辑发货信息
function editShipping(phone) {
    fetch(`/admin_get_shipping?phone=${encodeURIComponent(phone)}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 填充编辑表单
                document.getElementById('edit_shipping_phone').value = data.shipping.phone;
                document.getElementById('edit_shipping_status').value = data.shipping.status;
                document.getElementById('edit_shipping_tracking').value = '';  // 默认为空
                showModal('edit-shipping-modal');
            } else {
                showError(data.message || '获取发货信息失败');
            }
        })
        .catch(error => {
            showError('获取发货信息失败：' + error.message);
        });
}

// 更新物流单号
function updateTrackingNumber(phone, trackingNumber) {
    fetch('/admin_update_tracking', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            phone,
            tracking_number: trackingNumber
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('更新成功');
        } else {
            showError(data.message || '更新失败');
            refreshShippingList(); // 刷新列表以恢复原值
        }
    })
    .catch(error => {
        showError('更新失败：' + error.message);
        refreshShippingList(); // 刷新列表以恢复原值
    });
}

// 编辑金融卡信息
function editCard(cardNumber) {
    fetch(`/admin_get_card?number=${encodeURIComponent(cardNumber)}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 填充编辑表单
                document.getElementById('edit_card_number').value = data.card.card_number || data.card.number;
                // 移除金融卡等级的设置
                document.getElementById('edit_card_status').value = data.card.status;
                showModal('edit_card_modal');
            } else {
                showError(data.message || '获取金融卡信息失败');
            }
        })
        .catch(error => {
            showError('获取金融卡信息失败：' + error.message);
        });
}

// 提交编辑金融卡
function submitEditCard() {
    const cardNumber = document.getElementById('edit_card_number').value.trim();
    const status = document.getElementById('edit_card_status').value;
    
    if (!cardNumber) {
        showError('卡号不能为空');
        return;
    }
    
    fetch('/admin_update_card', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            card_number: cardNumber,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('金融卡修改成功', 'success');
            hideModal('edit_card_modal');
            refreshCardList();
        } else {
            showError(data.message || '修改失败');
        }
    })
    .catch(error => {
        console.error('修改金融卡错误:', error);
        showError('修改金融卡失败：' + error.message);
    });
}

// 添加金融卡提交函数
function submitAddCard() {
    const cardNumber = document.getElementById('add_card_number').value.trim();
    
    // 验证输入
    if (!cardNumber) {
        showError('请输入卡号');
        return;
    }
    
    // 验证卡号格式（1-19位数字）
    if (!/^\d{1,19}$/.test(cardNumber)) {
        showError('请输入1-19位数字的卡号');
        return;
    }
    
    // 发送请求
    fetch('/admin_add_card', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            card_number: cardNumber
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('金融卡添加成功', 'success');
            hideModal('add_card_modal');
            // 重置表单
            document.getElementById('add_card_number').value = '';
            // 刷新列表
            refreshCardList();
        } else {
            showError(data.message || '添加失败');
        }
    })
    .catch(error => {
        console.error('添加金融卡错误:', error);
        showError('添加金融卡失败：' + error.message);
    });
}

// 删除金融卡
function deleteCard(cardNumber) {
    if (!confirm('确定要删除该金融卡吗？')) {
        return;
    }

    fetch('/admin_delete_card', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ number: cardNumber })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('删除成功');
            refreshCardList();
        } else {
            showError(data.message || '删除失败');
        }
    })
    .catch(error => {
        showError('删除失败：' + error.message);
    });
}

// 编辑激活登记
function editActivation(id) {
    // 获取激活登记记录
    fetch(`/admin_get_activation?id=${id}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success || data.成功) {
                // 获取记录数据
                const activation = data.activation || data.激活登记;
                if (!activation) {
                    showError('未找到激活登记记录');
                    return;
                }
                
                // 填充表单
                document.getElementById('edit-activation-id').value = activation.id;
                document.getElementById('edit-activation-phone').value = activation.phone || '';
                document.getElementById('edit-activation-name').value = activation.name || '';
                document.getElementById('edit-activation-id-number').value = activation.id_number || '';
                document.getElementById('edit-activation-card-number').value = activation.card_number || '';
                document.getElementById('edit-activation-card-type').value = activation.card_type || 'platinum';
                
                // 显示模态框
                showModal('edit-activation-modal');
            } else {
                showError(data.message || data.消息 || '获取激活登记记录失败');
            }
        })
        .catch(error => {
            console.error('获取激活登记记录错误:', error);
            showError('获取激活登记记录失败：' + error.message);
        });
}

// 提交编辑激活登记
function submitEditActivation() {
    // 获取表单数据
    const id = document.getElementById('edit-activation-id').value;
    const phone = document.getElementById('edit-activation-phone').value.trim();
    const name = document.getElementById('edit-activation-name').value.trim();
    const idNumber = document.getElementById('edit-activation-id-number').value.trim();
    const cardNumber = document.getElementById('edit-activation-card-number').value.trim();
    const cardType = document.getElementById('edit-activation-card-type').value;
    
    // 表单验证
    if (!phone || !name || !cardNumber || !cardType) {
        showError('请填写所有必填字段');
        return;
    }
    
    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        showError('请输入有效的手机号码');
        return;
    }
    
    // 若填写身份证则校验格式
    if (idNumber && !/^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$/i.test(idNumber)) {
        showError('请输入有效的身份证号码');
        return;
    }
    
    // 发送请求
    fetch('/admin_update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            type: 'activation',
            data: {
                id: id,
                phone: phone,
                name: name,
                id_number: idNumber,
                card_number: cardNumber,
                card_type: cardType
            }
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('激活登记信息修改成功', 'success');
            hideModal('edit-activation-modal');
            
            // 刷新查询结果
            const searchInput = document.getElementById('search-input').value.trim();
            if (searchInput) {
                performSearch();
            }
        } else {
            showError(data.message || '激活登记信息修改失败');
        }
    })
    .catch(error => {
        console.error('修改激活登记信息错误:', error);
        showError('修改激活登记信息失败：' + error.message);
    });
}

// 编辑地址登记
function editAddress(id) {
    // 获取地址登记记录
    fetch(`/admin_get_address?id=${id}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success || data.成功) {
                // 获取记录数据
                const address = data.address || data.地址登记;
                if (!address) {
                    showError('未找到地址登记记录');
                    return;
                }
                
                // 填充表单
                document.getElementById('edit-address-id').value = address.id;
                document.getElementById('edit-address-phone').value = address.phone || '';
                document.getElementById('edit-address-name').value = address.name || '';
                document.getElementById('edit-address-id-number').value = address.id_number || '';
                document.getElementById('edit-address-delivery-phone').value = address.delivery_phone || '';
                document.getElementById('edit-address-delivery-address').value = address.delivery_address || '';
                document.getElementById('edit-address-card-type').value = address.card_type || 'platinum';
                document.getElementById('edit-address-shipping-status').value = address.shipping_status || 'pending';
                
                // 显示模态框
                showModal('edit-address-modal');
            } else {
                showError(data.message || data.消息 || '获取地址登记记录失败');
            }
        })
        .catch(error => {
            console.error('获取地址登记记录错误:', error);
            showError('获取地址登记记录失败：' + error.message);
        });
}

// 提交编辑地址登记
function submitEditAddress() {
    // 获取表单数据
    const id = document.getElementById('edit-address-id').value;
    const phone = document.getElementById('edit-address-phone').value.trim();
    const name = document.getElementById('edit-address-name').value.trim();
    const idNumber = document.getElementById('edit-address-id-number').value.trim();
    const deliveryPhone = document.getElementById('edit-address-delivery-phone').value.trim();
    const deliveryAddress = document.getElementById('edit-address-delivery-address').value.trim();
    const cardType = document.getElementById('edit-address-card-type').value;
    const shippingStatus = document.getElementById('edit-address-shipping-status').value;
    
    // 表单验证
    if (!phone || !name || !deliveryPhone || !deliveryAddress || !cardType) {
        showError('请填写所有必填字段');
        return;
    }
    
    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        showError('请输入有效的手机号码');
        return;
    }
    
    // 若填写身份证则校验格式
    if (idNumber && !/^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$/i.test(idNumber)) {
        showError('请输入有效的身份证号码');
        return;
    }
    
    // 验证收货电话格式
    if (!/^1[3-9]\d{9}$/.test(deliveryPhone)) {
        showError('请输入有效的收货电话');
        return;
    }
    
    // 发送请求
    fetch('/admin_update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            type: 'address',
            data: {
                id: id,
                phone: phone,
                name: name,
                id_number: idNumber,
                delivery_phone: deliveryPhone,
                delivery_address: deliveryAddress,
                card_type: cardType,
                shipping_status: shippingStatus
            }
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('地址登记信息修改成功', 'success');
            hideModal('edit-address-modal');
            
            // 刷新查询结果
            const searchInput = document.getElementById('search-input').value.trim();
            if (searchInput) {
                performSearch();
            }
        } else {
            showError(data.message || '地址登记信息修改失败');
        }
    })
    .catch(error => {
        console.error('修改地址登记信息错误:', error);
        showError('修改地址登记信息失败：' + error.message);
    });
}

// 删除激活登记信息
function deleteActivation(id, phone) {
    if (!confirm(`确定要删除 ${phone} 的激活登记信息吗？此操作不可恢复！`)) {
        return;
    }

    fetch('/admin_delete_record', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            type: 'activation',
            id: id
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('激活登记信息删除成功', 'success');
            
            // 刷新查询结果
            const searchInput = document.getElementById('search-input').value.trim();
            if (searchInput) {
                performSearch();
            }
        } else {
            showError(data.message || '删除失败');
        }
    })
    .catch(error => {
        console.error('删除激活登记信息错误:', error);
        showError('删除激活登记信息失败：' + error.message);
    });
}

// 删除地址登记信息
function deleteAddress(id, phone) {
    if (!confirm(`确定要删除 ${phone} 的地址登记信息吗？此操作不可恢复！`)) {
        return;
    }

    fetch('/admin_delete_record', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            type: 'address',
            id: id
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('地址登记信息删除成功', 'success');
            
            // 刷新查询结果
            const searchInput = document.getElementById('search-input').value.trim();
            if (searchInput) {
                performSearch();
            }
        } else {
            showError(data.message || '删除失败');
        }
    })
    .catch(error => {
        console.error('删除地址登记信息错误:', error);
        showError('删除地址登记信息失败：' + error.message);
    });
}

// 搜索发货信息
function searchShipping() {
    const searchInput = document.getElementById('shipping-search-input').value.trim();
    if (!searchInput) {
        showError('请输入手机号码');
        return;
    }
    
    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(searchInput)) {
        showError('请输入有效的手机号码');
        return;
    }
    
    fetch(`/admin_search_shipping?phone=${encodeURIComponent(searchInput)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                if (data.records && data.records.length > 0) {
                    updateShippingList(data.records);
                    showError(`已找到 ${data.records.length} 条记录`, 'success');
                } else {
                    updateShippingList([]);
                    showError('未找到相关记录');
                }
            } else {
                showError(data.message || '查询失败');
            }
        })
        .catch(error => {
            console.error('查询发货信息错误:', error);
            showError('查询失败：' + error.message);
        });
}

// 批量选择所有发货记录
function toggleAllShipping() {
    const masterCheckbox = document.getElementById('select-all-shipping');
    const checkboxes = document.querySelectorAll('#shipping-table tbody input[type="checkbox"]');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = masterCheckbox.checked;
    });
}

// 根据状态批量更新发货状态
function batchUpdateShippingWithStatus() {
    const selectedRows = document.querySelectorAll('#shipping-table input[type="checkbox"]:checked');
    if (!selectedRows.length) {
        showError('请选择要更新的记录');
        return;
    }

    const phones = Array.from(selectedRows).map(checkbox => checkbox.value);
    const status = document.getElementById('batch-status-select').value;
    
    if (!confirm(`确定要将选中的 ${phones.length} 条记录状态改为 ${getShippingStatusName(status)} 吗？`)) {
        return;
    }
    
    fetch('/update_shipping_status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            phones: phones,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError(`成功更新 ${phones.length} 条记录`, 'success');
            refreshShippingList();
        } else {
            showError(data.message || '更新失败');
        }
    })
    .catch(error => {
        console.error('批量更新发货状态错误:', error);
        showError('更新失败：' + error.message);
    });
}

// 通过批量输入的手机号更新发货状态
function batchUpdateByPhones() {
    const phonesText = document.getElementById('batch-phones-textarea').value.trim();
    if (!phonesText) {
        showError('请输入手机号码');
        return;
    }
    
    // 解析输入的手机号码
    const phones = phonesText.split('\n')
        .map(phone => phone.trim())
        .filter(phone => phone && /^1[3-9]\d{9}$/.test(phone));
    
    if (phones.length === 0) {
        showError('未找到有效的手机号码');
        return;
    }
    
    const status = document.getElementById('batch-phones-status').value;
    
    if (!confirm(`确定要将输入的 ${phones.length} 个手机号的发货状态改为 ${getShippingStatusName(status)} 吗？`)) {
        return;
    }
    
    fetch('/update_shipping_status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            phones: phones,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError(`成功更新 ${data.updated_count || phones.length} 条记录，${data.not_found || 0} 条记录未找到`, 'success');
            hideModal('batch-phones-modal');
            document.getElementById('batch-phones-textarea').value = '';
            refreshShippingList();
        } else {
            showError(data.message || '更新失败');
        }
    })
    .catch(error => {
        console.error('批量更新发货状态错误:', error);
        showError('更新失败：' + error.message);
    });
}

// 导出地址登记数据
function exportAddressData() {
    // 构建导出条件
    const conditions = {
        // 卡片等级过滤
        card_type_enabled: document.getElementById('export-card-level-check').checked,
        card_type: document.getElementById('export-card-level').value,
        
        // 发货状态过滤
        shipping_status_enabled: document.getElementById('export-shipping-status-check').checked,
        shipping_status: document.getElementById('export-shipping-status').value,
        
        // 数量限制
        limit_enabled: document.getElementById('export-limit-check').checked,
        limit_count: document.getElementById('export-limit-count').value,
        
        // 日期范围
        date_enabled: document.getElementById('export-date-check').checked,
        date_start: document.getElementById('export-date-start').value,
        date_end: document.getElementById('export-date-end').value
    };
    
    // 如果没有启用任何过滤条件，确认是否导出所有数据
    const hasFilters = conditions.card_type_enabled || 
                       conditions.shipping_status_enabled || 
                       conditions.limit_enabled || 
                       conditions.date_enabled;
                       
    if (!hasFilters && !confirm('未设置任何过滤条件，将导出所有地址登记数据。是否继续？')) {
        return;
    }
    
    // 如果没有设置数量限制，且未设置其他过滤条件，建议添加数量限制
    if (!conditions.limit_enabled && !hasFilters) {
        const setLimit = confirm('建议添加数量限制以避免导出过多数据。是否添加默认的1000条限制？');
        if (setLimit) {
            conditions.limit_enabled = true;
            conditions.limit_count = 1000;
            document.getElementById('export-limit-check').checked = true;
            document.getElementById('export-limit-count').disabled = false;
            document.getElementById('export-limit-count').value = 1000;
        }
    }
    
    // 提示用户导出正在处理
    showError('正在准备导出数据，请稍候...', 'warning');
    
    // 发送POST请求到后端API
    const formData = new FormData();
    formData.append('conditions', JSON.stringify(conditions));
    
    fetch('/api/admin/export', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        // 检查响应状态
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('未找到符合条件的数据');
            }
            throw new Error(`服务器错误：${response.status}`);
        }
        
        // 检查内容类型
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            // 如果是JSON响应，可能是错误信息
            return response.json().then(data => {
                throw new Error(data.message || '导出失败');
            });
        }
        
        // 处理CSV文件下载
        return response.blob();
    })
    .then(blob => {
        // 创建下载链接
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        
        // 生成文件名
        const date = new Date().toISOString().slice(0, 10);
        a.download = `地址登记数据_${date}.csv`;
        
        // 触发下载
        document.body.appendChild(a);
        a.click();
        
        // 清理
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        // 显示成功消息
        showError('数据导出成功', 'success');
    })
    .catch(error => {
        console.error('导出失败:', error);
        showError('导出失败: ' + error.message);
    });
}

// 提交编辑发货信息
function submitEditShipping() {
    const phone = document.getElementById('edit_shipping_phone').value.trim();
    const status = document.getElementById('edit_shipping_status').value;
    
    // 验证手机号
    if (!phone) {
        showError('手机号码不能为空');
        return;
    }
    
    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        showError('请输入有效的手机号码');
        return;
    }
    
    // 验证状态值
    const validStatuses = ['pending', 'shipped', 'cancelled'];
    if (!validStatuses.includes(status)) {
        showError('无效的发货状态');
        return;
    }
    
    // 准备请求数据
    const requestData = {
        phone: phone,
        status: status
    };
    
    // 发送更新请求
    fetch('/admin_update_shipping', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            showError('发货信息更新成功', 'success');
            hideModal('edit-shipping-modal');
            refreshShippingList(); // 刷新列表
        } else {
            showError(data.message || '更新失败');
        }
    })
    .catch(error => {
        console.error('更新发货信息错误:', error);
        showError('更新发货信息失败：' + error.message);
    });
}

// 打开编辑发货信息模态框
function openEditShippingModal(phone, currentStatus, trackingNumber) {
    // 设置表单字段的值
    document.getElementById('edit_shipping_phone').value = phone;
    document.getElementById('edit_shipping_status').value = currentStatus || 'pending';
    document.getElementById('edit_shipping_tracking').value = trackingNumber || '';
    
    // 显示模态框
    showModal('edit-shipping-modal');
}

// 提交编辑账户
function submitEditAccount() {
    const phone = document.getElementById('edit_account_phone').value.trim();
    const cardLevel = document.getElementById('edit_account_card_level').value.trim();
    
    // 验证输入
    if (!phone) {
        showError('手机号码不能为空');
        return;
    }
    if (!cardLevel) {
        showError('请选择金融卡等级');
        return;
    }

    // 验证手机号格式
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        showError('请输入有效的手机号码');
        return;
    }

    // 验证金融卡等级
    const validLevels = ['platinum', 'black', 'supreme'];
    if (!validLevels.includes(cardLevel)) {
        showError('请选择有效的金融卡等级');
        return;
    }
    
    // 发送更新请求
    fetch('/admin_update_account', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            phone: phone,
            card_level: cardLevel
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showError('账户修改成功', 'success');
            hideModal('edit_account_modal');
            // 刷新账户列表
            refreshAccountList();
        } else {
            showError(data.message || '修改失败');
        }
    })
    .catch(error => {
        console.error('修改账户错误:', error);
        showError('修改账户失败：' + error.message);
    });
} 