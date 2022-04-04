from odoo import _, api, fields, models

class CostSheet(models.Model):
    _name = 'cost.sheet'
    _description = 'Cost Sheet'
    _inherit = ['portal.mixin','mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Name',tracking=True)
    crm_id = fields.Many2one('crm.lead', string='CRM',tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    date_document = fields.Date('Request Date',tracking=True,default=fields.Date.today)
    user_id = fields.Many2one('res.users', string='Responsible',default=lambda self:self.env.user.id)
    rab_template_id = fields.Many2one('rab.template', string='RAB Template',tracking=True)
    line_ids = fields.One2many('project.rab', 'cost_sheet_id', string='RAB')  
    note = fields.Text('Term and condition')
    approval_id = fields.Many2one('approval.approval', string='Approval')
    approver_id = fields.Many2one('approver.line', string='Approver')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submited'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
    ], string='Status',tracking=True, default="draft")
    
    state_rap = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submited'),
        ('waiting', 'Waiting Approval'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
    ], string='Status',tracking=True, default="draft")
    margin_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('amount', 'Amount'),
    ], string='Margin Type',default='percentage')
    margin_amount_input = fields.Monetary('Margin Amount')
    margin_percent_input = fields.Float('Margin %')
    

    # purchase_id = fields.Many2one('purchase.requisition', string='Purchase')

    total_amount = fields.Float(compute='_compute_total_amount', string='Total Amount',store=True)
    total_margin = fields.Float(compute='_compute_total_amount', string='Total Margin',store=True)
    total_without_margin = fields.Float(compute='_compute_total_amount', string='Price Subtotal',store=True)
    currency_id = fields.Many2one('res.currency', string='currency',default=lambda self:self.env.company.currency_id.id)

    
    def action_create_requisition(self):
        request = self.env['purchase.requisition'].create({
            'user_id': self.env.uid,
            'ordering_date': fields.Date.today(),
            'origin': self.name,
            'line_ids':[(0,0,{
                'product_id':data.product_id.id,
                'product_description_variants': data.product_id.name,
                'product_qty': data.product_qty,
                'price_unit': data.price_unit
            })for data in self.line_ids if not data.display_type]
        })
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "purchase.requisition",
            "res_id": request.id
        }
    
    @api.depends('margin_amount_input','margin_percent_input')
    def _compute_total_amount(self):
        for this in self:
            total = 0
            total_without_margin = 0
            total_margin = 0
            if this.margin_type == 'percentage':
 
                total = sum(this.line_ids.mapped('price_subtotal'))
                total_without_margin = sum(this.line_ids.mapped('price_unit'))
                total_margin = sum(this.line_ids.mapped('margin'))
            else:

                total = sum(this.line_ids.mapped('price_subtotal')) + this.margin_amount_input
                total_without_margin = sum(this.line_ids.mapped('price_unit'))
                total_margin = this.margin_amount_input
                
            this.total_amount = total
            this.total_without_margin = total_without_margin
            this.total_margin = total_margin

    
    @api.onchange('margin_type')
    def _onchange_margin_type(self):
        self.margin_amount_input = 0.0
        self.margin_percent_input = 0.0
    
    @api.onchange('margin_percent_input')
    def _onchange_margin_percent_input(self):
        if self.margin_percent_input:
            self.line_ids.write({'margin_percent':self.margin_percent_input})
        else:
            self.line_ids.write({'margin_percent':self.margin_percent_input})
            
    
    @api.onchange('crm_id')
    def _onchange_crm_id(self):
        if self.crm_id and self.crm_id.partner_id:
            self.partner_id = self.crm_id.partner_id.id
    
    @api.depends('approver_id','approval_id')
    def _compute_is_approver(self):
        for this in self:
            if this.approval_id or this.approver_id:
                if this.approval_id.approval_type == 'user':
                    this.is_approver = this.env.user.id in this.approver_id.user_ids.ids
                else:
                    this.is_approver = this.env.user.id in this.approver_id.group_ids.users.ids
            else:
                this.is_approver = False

    def waiting_approval(self):
        for request in self:
            request.approval_id = request.env['approval.approval'].search([('active', '=', True)],limit=1)
            if bool(request.approver_id):
                approver_id = request.approval_id.approver_line_ids.search([("amount", "<=", request.total_amount),('sequence','>',request.approver_id.sequence)],limit=1)
                if approver_id:
                    request.write({"approver_id": approver_id.id})
                    # request.notify()
                else:
                    request.write({"state_rap": "done","approver_id":False })

            else:
                approver_id = request.approval_id.approver_line_ids.search([("amount", "<=", request.total_amount)],order="sequence ASC",limit=1)
                if approver_id:
                    request.write(
                        {
                            "approver_id": approver_id.id,
                            "state_rap": "waiting",
                        }
                    )
                    # request.notify()
                else:
                    request.write(
                        {
                            "state_rap": "done",
                            "approver_id":False
                        }
                    )
                    

    def action_submit(self):
        self.write({'state':'submit'})
    def action_done(self):
        self.write({'state':'done'})
    def action_to_draft(self):
        self.write({'state':'draft'})
    
    # def create_rap(self):
    #     purchase = self.env['purchase.requisition'].create({
    #         'crm_id': self.crm_id.id,
    #         'origin': self.name,
    #         'date_end' : fields.Datetime.today,
    #         'ordering_date' : fields.Date.today,
    #         'schedule_date' : fields.Date.today,
    #         'line_ids': [(0,0,{
    #             'product_id': template.product_id.id,
    #             'product_qty': template.product_qty,
    #             'product_uom_id': template.uom_id.id,
    #             'product_description_variants' : template.name,
    #             'price_unit': template.price_unit
    #         }) for template in self.line_ids]

    #     })
    #     self.write({'purchase_id':purchase.id})
        
    #     return {
    #         "type": "ir.actions.act_window",
    #         "view_mode": "form",
    #         "res_model": "purchase.requisition",
    #         "res_id": purchase.id
    #     }

    def action_view_crm(self):
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "crm.lead",
            "res_id": self.crm_id.id
        }
        
    def action_print_rab(self):
        return self.env.ref('solinda_cost_sheet.action_report_cost_sheet').report_action(self)

    @api.model
    def create(self, vals):
        res = super(CostSheet, self).create(vals)
        res.name = self.env["ir.sequence"].next_by_code("cost.sheet.seq")
        res.crm_id.rab_id = res.id
        return res 
    
   
    @api.onchange('rab_template_id')
    def _onchange_rab_template_id(self):
        if self.line_ids:
            self.write({
                'line_ids': [(5,0,0)]
            })
        else:        
            self.write({
                'line_ids': [(0,0,{
                    'name': template.name,
                    'display_type': template.display_type,
                    'sequence': template.sequence,
                    'product_id': template.product_id.id,
                    'product_qty': template.product_qty,
                    'uom_id': template.uom_id.id,
                    'vol_factor': template.vol_factor,
                    'item_factor': template.item_factor,
                    'lab_factor': template.lab_factor,
                    'start_date': template.start_date,
                    'end_date': template.end_date,
                    'no_pos': template.no_pos,
                    'price_unit': template.price_unit,
                    'margin_percent': template.margin_percent
                }) for template in self.rab_template_id.line_ids]
        }) 

# RAB 

class ProjectRab(models.Model):
    _name = 'project.rab'
    _description = 'Project RAB'

    cost_sheet_id = fields.Many2one('cost.sheet', string='Cost Sheet')
    rab_template_id = fields.Many2one('rab.template', string='RAB Template')
    # project_id = fields.Many2one('project.project', string='Project')
    display_type = fields.Selection([
        ('line_section', "Section"),
        ('line_note', "Note")], default=False, help="Technical field for UX purpose.")
    sequence = fields.Integer('Sequence')

    product_id = fields.Many2one('product.product', string='Product')
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', readonly=True)

    name = fields.Char('Description')
    
    product_qty = fields.Float('Quantity',default=1.0)
    uom_id = fields.Many2one('uom.uom', string='UoM')
    vol_factor = fields.Float('Volume Factor')
    item_factor = fields.Float('Item Factor')
    lab_factor = fields.Float('Lab Factor')
    price_unit = fields.Float('Price')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('Finish Date')
    no_pos = fields.Char('No')
    margin = fields.Float('Margin',compute='_compute_price')
    margin_percent = fields.Float(string='Margin Percent',compute='_compute_price')
    price_subtotal = fields.Float(compute='_compute_price', string='Subtotal')
    
    
    def create_requisition(self):
        request = self.env['purchase.requisition'].create({
            'user_id': self.env.uid,
            'ordering_date': fields.Date.today(),
            'origin': self.cost_sheet_id.name,
            'line_ids':[(0,0,{
                'product_id':self.product_id.id,
                'product_qty': self.product_qty,
                'price_unit': self.price_unit
            })]
        })
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "purchase.requisition",
            "res_id": request.id
        }


    
    @api.depends('price_unit','cost_sheet_id.margin_percent_input','cost_sheet_id.margin_amount_input')
    def _compute_price(self):
        for this in self:
            margin = 0.0
            margin_percent = 0.0
            subtotal = 0.0
            if this.cost_sheet_id.margin_type == 'percentage':
                margin_percent = this.cost_sheet_id.margin_percent_input
                margin = this.price_unit * margin_percent
                subtotal = this.price_unit * this.product_qty + margin
            else:
                margin_percent = 0.0
                margin = 0.0
                subtotal = this.price_unit * this.product_qty 
               
                
            this.margin = margin
            this.margin_percent = margin_percent
            this.price_subtotal = subtotal
            


class RabTemplate(models.Model):
    _name = 'rab.template'
    _description = 'RAB Template'

    name = fields.Char('Name of Template')
    line_ids = fields.One2many('project.rab', 'rab_template_id', string='Rab Line')

    
