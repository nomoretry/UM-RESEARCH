"""Linear-fractional dispatch with port power as the normalization scale.

u=50/P, grid quantities x=e*u, battery states S=SOC*u and warehouse meter
w=W*u. One E1 port quarter grants 50*(15/60) normalized kWh irrespective of
P: its integer number of reservations no longer multiplies a continuous peak.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from heapq import heappop, heappush
from math import ceil
from time import perf_counter

import numpy as np
from scipy.optimize._highspy import _core as highs_core
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, vstack

from .energy_boundary import A, Matrix
from .fleet_service import SITES, subset_case


class _EmptyBox(Exception):
    pass


def _capped_support(local, relaxed, cutoff, gap):
    """Compute min(cutoff, true support) with one additional binary.

    At dummy=1 translate just the integer variables by their fractional
    residuals in the LP solution. Its rounded integer coordinates then give
    a known feasible solution costing exactly cutoff. The explicit LP lower
    bound makes every dummy solution cost at least cutoff. At dummy=0 there
    is no translation and the original integer problem is unchanged.
    """
    from .cabinet_model import _bounded_mip
    model=deepcopy(local)
    shift=np.zeros(len(local.cost))
    integer=np.asarray(local.integer,dtype=bool)
    shift[integer]=relaxed.x[integer]-np.rint(relaxed.x[integer])
    adjustment=float(np.dot(shift,local.cost))
    dummy=model.var(0,1,cutoff-relaxed.fun+adjustment,integer=True)
    translated=np.bincount(model.row,weights=np.asarray(model.data)*shift[model.col],
                           minlength=len(model.lb))
    for row in np.flatnonzero(translated):
        model.row.append(int(row))
        model.col.append(dummy)
        model.data.append(translated[row])
    model.add([(i,c) for i,c in enumerate(local.cost) if c]+[(dummy,adjustment)],
              low=relaxed.fun-1e-8)
    result=_bounded_mip(model,cutoff+1e-7,gap,start=np.r_[relaxed.x-shift,1.])
    if result.status!=0:
        raise ArithmeticError(("capped weekly support",result.message))
    raw=getattr(result,"mip_dual_bound",None)
    return result,float(result.fun if raw is None else raw),bool(result.x[dummy]<.5)


def _adaptive_price(local, relaxed, ceiling, tolerance, capped):
    """Enforce only reservation groups obstructing physical reconstruction.

    Every intermediate problem is an exact relaxation of weekly pricing.
    The physical energy determines whether unused fractional count variables
    can be replaced by actual quarters. A dummy optimum already supplies the
    capped lower bound, irrespective of the remaining groups.
    """
    from .cabinet_model import _bounded_mip
    integral=local.integer.copy()
    local.integer=[False]*len(integral)
    r=relaxed
    bound=best_bound=r.fun
    real=True
    enabled=set()
    rounds=[]
    def result():
        r.reservation_rounds=rounds
        return r,best_bound,real
    for iteration in range(len(local.reservations)+2):
        failed=[]
        for j,(count,slot,items) in enumerate(local.reservations):
            energies=[sum(r.x[i] for i in indices) for _,indices in items]
            used=(sum(max(0,ceil(v/slot-1e-8)) for v in energies) if slot else sum(v>1e-8 for v in energies))
            if used>count:
                failed.append(j)
        if not failed:
            return result()
        if enabled.intersection(failed):
            raise ArithmeticError(("enabled weekly group cannot be reconstructed",failed))
        if iteration>=4:
            failed=[j for j in range(len(local.reservations)) if j not in enabled]
        for j in failed:
            for z,_ in local.reservations[j][2]:
                local.integer[z]=integral[z]
        enabled.update(failed)
        if capped:
            r,bound,real=_capped_support(local,relaxed,ceiling,tolerance)
        else:
            r=_bounded_mip(local,ceiling,tolerance)
            raw=getattr(r,"mip_dual_bound",None)
            bound=float(r.fun if raw is None else raw)
        if r.status!=0:
            raise ArithmeticError(("weekly reservation pricing",r.message))
        best_bound=max(best_bound,bound)
        rounds.append(dict(active_groups=len(enabled),status=r.message,status_code=r.status,
                           objective=r.fun,dual_bound=getattr(r,"mip_dual_bound",None),
                           gap=getattr(r,"mip_gap",None),real=real))
        if not real:
            return result()
    raise ArithmeticError("Unresolved weekly reservation groups")


def _support_prices(history, corners, c_u, c_w):
    """Choose the next supporting slopes using feasible weekly columns."""
    names=[r["component"] for r in history[0]]
    n=len(names)
    dim=3*n+1
    rows=[]
    rhs=[]
    for batch in history:
        for j,r in enumerate(batch):
            row=np.zeros(dim)
            row[j]=1
            row[n+j]=-r["u"]
            row[2*n+j]=-r["w"]
            rows.append(row)
            rhs.append(r["normalized_energy"])
    for uu,ww in corners:
        row=np.zeros(dim)
        row[-1]=1
        row[n:2*n]=uu
        row[2*n:3*n]=ww
        rows.append(row)
        rhs.append(c_u*uu+c_w*ww)
    last=history[-1]
    # Trust intervals stabilize slope selection when early columns leave a
    # direction unidentified. They only choose valid supporting inequalities.
    du=max(max(x[0] for x in corners)-min(x[0] for x in corners),1e-6)
    dw=max(max(x[1] for x in corners)-min(x[1] for x in corners),1e-6)
    width_u=max(2.,3./du)
    width_w=max(2.,3./dw)
    bounds=[(None,None)]*n+[(r["alpha"]-width_u,r["alpha"]+width_u) for r in last]
    bounds += [(r["beta"]-width_w,r["beta"]+width_w) for r in last]+[(None,None)]
    result=linprog(np.r_[[-1.]*n,[0.]*(2*n),-1.],A_ub=rows,b_ub=rhs,bounds=bounds,method="highs")
    if not result.success:
        raise ArithmeticError(("support slope selection",result.message))
    return {name:(result.x[n+j],result.x[2*n+j]) for j,name in enumerate(names)}


def _weekly_support(m, owners, u, w, energy_cost, ceiling, integer, tolerance, fraction, history, corners,
                    capped=False):
    """Add separable, valid weekly lower bounds at the master LP shadow prices.

    Independent weeks share only u and w. For ANY coefficients a,b, a weekly
    optimum of energy+a*u+b*w is a valid affine lower bound on weekly energy.
    The continuous dual chooses the coefficients. A global cost ceiling also
    bounds each week's individually nonnegative excess over its LP support.
    """
    from .cabinet_model import _bounded_mip
    a=coo_matrix((m.data,(m.row,m.col)),shape=(len(m.lb),len(m.cost))).tocsr()
    lower,upper=np.asarray(m.lb),np.asarray(m.ub)
    eq=lower==upper
    le=np.isfinite(upper)&~eq
    ge=np.isfinite(lower)&~eq
    lp=linprog(m.cost,A_eq=a[eq],b_eq=lower[eq],A_ub=vstack((a[le],-a[ge])),
               b_ub=np.r_[upper[le],-lower[ge]],bounds=np.column_stack((m.lower,m.upper)),method="highs",
               options={"dual_feasibility_tolerance":1e-9,"primal_feasibility_tolerance":1e-9})
    if not lp.success:
        if capped and lp.status==2:
            raise _EmptyBox(lp.message)
        raise ValueError(("weekly support LP",lp.message))
    if capped and lp.fun>=ceiling-1e-8:
        return lp.fun,[],None,{}
    dual=np.zeros(len(lower))
    dual[eq]=lp.eqlin.marginals
    dual[le]+=lp.ineqlin.marginals[:int(le.sum())]
    dual[ge]-=lp.ineqlin.marginals[int(le.sum()):]
    row_owner=[]
    for row in range(a.shape[0]):
        seen={owners[i] for i in a.indices[a.indptr[row]:a.indptr[row+1]] if i in owners}
        if len(seen)>1:
            raise ArithmeticError(("cross-component row",seen))
        row_owner.append(next(iter(seen),None))
    records=[]
    values=np.zeros(len(m.cost))
    denominators={}
    prices=_support_prices(history,corners,m.cost[u],m.cost[w]) if history else {}
    blocks=[]
    for name in sorted(set(owners.values())):
        selected=np.array([r==name for r in row_owner])
        cols=[u,w,*[i for i,owner in owners.items() if owner==name]]
        rows=np.array([r is None or r==name for r in row_owner])
        alpha,beta=np.asarray(a[selected][:,[u,w]].T@dual[selected]).ravel()
        if prices:
            alpha,beta=prices[name]
        local=Matrix()
        local.cost=[alpha,beta,*[energy_cost[i] for i in cols[2:]]]
        local.lower=[m.lower[i] for i in cols]
        local.upper=[m.upper[i] for i in cols]
        local.integer=[integer[i] for i in cols]
        lookup={col:i for i,col in enumerate(cols)}
        local.reservations=[(n,slot,[(lookup[z],[lookup[i] for i in indices]) for z,indices in items])
                            for n,slot,items in m.reservations if items[0][0] in lookup]
        local.lb,local.ub=lower[rows].tolist(),upper[rows].tolist()
        mat=a[rows][:,cols].tocoo()
        local.row,local.col,local.data=mat.row.tolist(),mat.col.tolist(),mat.data.tolist()
        local.integer,unrelaxed=[False]*len(cols),local.integer
        low=local.solve()
        if low.status!=0:
            raise ArithmeticError(("local support LP",name,low.message))
        local.integer=unrelaxed
        blocks.append((name,cols,local,low.fun,alpha,beta,low))
    residual=min((m.cost[u]-sum(b[4] for b in blocks))*uu+(m.cost[w]-sum(b[5] for b in blocks))*ww
                 for uu,ww in corners)
    slack=max(0.,ceiling-residual-sum(b[3] for b in blocks))+1e-6
    dual_bound=residual
    remaining=sum(b[3] for b in blocks)
    if capped and history:
        last={record["component"]:record for record in history[-1]}
        def previous_penalty(block):
            r=last[block[0]]
            v=r["certified_lower"]
            return v-r["support_at_lp"]
        blocks.sort(key=previous_penalty,reverse=True)
    def price(block):
        name,cols,local,at_lp,alpha,beta,relaxed=block
        t=perf_counter()
        # Support cuts use the returned dual bound even if the local incumbent
        # and bound differ; the final global certificate uses its own tolerance.
        if capped:
            feasible=[]
            min_u,max_u=min(x for x,_ in corners),max(x for x,_ in corners)
            min_w,max_w=min(y/x for x,y in corners),max(y/x for x,y in corners)
            for batch in history:
                for prior in batch:
                    if prior["component"]!=name or not prior["real"]:
                        continue
                    uu,ww=prior["u"],prior["w"]
                    if min_u<=uu<=max_u and min_w<=ww/uu<=max_w:
                        feasible.append(prior["normalized_energy"]+alpha*uu+beta*ww)
            if feasible:
                r,bound,real=_adaptive_price(local,relaxed,min(feasible)+1e-6,max(tolerance,fraction*slack),False)
            else:
                local_tol=max(tolerance,fraction*slack)
                r,bound,real=_adaptive_price(local,relaxed,at_lp+slack+2*local_tol+1e-6,local_tol,True)
        else:
            r,bound,real=_adaptive_price(local,relaxed,at_lp+slack,max(tolerance,fraction*slack),False)
        return r,bound,real,perf_counter()-t

    # Every root pricing problem is independent. Only the deterministic
    # component order is used when combining its lower bounds and schedules.
    if capped or len(blocks)==1:
        priced=map(price,blocks)
    else:
        with ThreadPoolExecutor(max_workers=min(4,len(blocks))) as pool:
            priced=list(pool.map(price,blocks))
    for block,(r,bound,real,seconds) in zip(blocks,priced):
        name,cols,local,at_lp,alpha,beta,relaxed=block
        remaining-=at_lp
        if r.status!=0:
            raise ArithmeticError(("weekly support",name,r.message))
        raw=getattr(r,"mip_dual_bound",None)
        dual_bound+=bound
        m.add([(i,c) for i,c in zip(cols,local.cost) if c],low=bound-1e-7)
        if real:
            values[cols[2:]]=r.x[2:len(cols)]
            denominators[name]=r.x[0]
        records.append(dict(component=name,status=r.message,status_code=r.status,objective=r.fun,
                            dual_bound=raw,gap=getattr(r,"mip_gap",None),certified_lower=bound,
                            reservation_rounds=r.reservation_rounds,alpha=alpha,beta=beta,
                            real=real,u=r.x[0],w=r.x[1],
                            normalized_energy=float(np.dot(local.cost[2:],r.x[2:len(cols)])),
                            support_at_lp=at_lp,seconds=seconds))
        if capped and dual_bound+remaining-1e-7*len(blocks)>=ceiling-tolerance:
            return max(lp.fun,dual_bound+remaining-1e-7*len(blocks)),records,None,{}
    records.sort(key=lambda r:r["component"])
    return max(lp.fun,dual_bound-1e-7*len(blocks)),records,(values if len(denominators)==len(blocks) else None),denominators


def _decode(period,groups,levels,values,by_date,denominators):
    schedule=[]
    for day,site,count,reservations,decisions in groups:
        u=denominators[by_date[day]]
        cursor=0
        for a,b,v,i in decisions:
            normalized=values[i]
            if normalized<=1e-8:
                continue
            if reservations:
                number=max(1,ceil(normalized/(50.*(b-a)/60)-1e-8))
                slots=range(cursor,cursor+number)
                cursor+=number
                if cursor>count:
                    raise ArithmeticError(("normalized slots",day,site,count,decisions))
            else:
                slots=range(count)
            kw=normalized/u*60/((b-a)*len(slots))
            off=period.offset[day]
            for j in slots:
                left=off+a+15*j
                schedule.append(dict(date=day,site=site,vehicle_id=v,start_min=left,end_min=off+b+15*j,
                                     reservation_slot=int(left//15),power_kw=kw))
    states=[dict(date=d,vehicle_id=v,served=True,x=values[x]/denominators[by_date[d]],
                 y=values[y]/denominators[by_date[d]]) for (d,v),(x,y) in levels.items()]
    return dict(schedule=schedule,states=states)


def _bill(p, rows, energy_weight, site_weights, weights):
    energy=0.
    loads=defaultdict(float)
    for r in rows:
        d,site=r["date"],r["site"]
        q=r["reservation_slot"]
        kwh=r["power_kw"]*(r["end_min"]-r["start_min"])/60
        hour=(q-p.offset[d]//15)//4
        energy+=kwh*(energy_weight*p.prices[d][hour]/1000+site_weights.get(site,0))
        loads[site,q]+=4*kwh
    return energy+sum(weights[s]*max((v for (site,_),v in loads.items() if site==s),default=0.)
                      for s in SITES)


def _schedule_columns(p,witness,by_date,energy_weight,site_weights):
    """A common feasible meter setting gives one priced column per week."""
    rows=witness["schedule"]
    port=_bill(p,rows,0.,{},{"PORT":1.,"WAREHOUSE":0.})
    if port<=0.:
        return []
    u=50./port
    w=u*_bill(p,rows,0.,{},{"PORT":0.,"WAREHOUSE":1.})
    grouped=defaultdict(list)
    for r in rows:
        grouped[by_date[r["date"]]].append(r)
    return [dict(component=name,u=u,w=w,real=True,
                 normalized_energy=u*_bill(p,grouped[name],energy_weight,site_weights,dict.fromkeys(SITES,0.)))
            for name in sorted(set(by_date.values()))]


def _competitive_box(m,u,w,box,numerator,cutoff,port_constant):
    """Project the common master LP cost sublevel onto both site meters.

    Previously proved integer weekly support cuts remain in this LP. Only
    points costing at most cutoff can improve the certificate; any removed
    part of the parent therefore has the separately recorded bound cutoff.
    """
    ul,uh,wl,wh=box
    a=coo_matrix((m.data,(m.row,m.col)),shape=(len(m.lb),len(m.cost))).tocsr()
    lower,upper=np.asarray(m.lb),np.asarray(m.ub)
    eq=lower==upper
    le=np.isfinite(upper)&~eq
    ge=np.isfinite(lower)&~eq
    level=np.asarray(numerator).copy()
    level[u]-=cutoff
    a_ub=vstack((a[le],-a[ge],coo_matrix(level[np.newaxis,:])))
    rhs=np.r_[upper[le],-lower[ge],-port_constant+1e-7]
    limits=np.column_stack((m.lower,m.upper))
    results=[]
    for col,sign in ((u,1.),(u,-1.),(w,1.),(w,-1.)):
        c=np.zeros(len(m.cost))
        c[col]=sign
        r=linprog(c,A_eq=a[eq],b_eq=lower[eq],A_ub=a_ub,b_ub=rhs,bounds=limits,
                  method="highs",options={"dual_feasibility_tolerance":1e-9,"primal_feasibility_tolerance":1e-9})
        if r.status==2:
            return None,results
        if not r.success:
            raise ArithmeticError(("meter domain projection",r.message))
        results.append(float(r.fun*sign))
    left=max(ul,results[0]-1e-7)
    right=min(uh,results[1]+1e-7)
    low=max(wl,(results[2]-1e-7)/right)
    high=min(wh,(results[3]+1e-7)/left)
    return (left,right,low,high),results


def _spatial(m, owners, u, w, numerator, integer, bounds, port_constant, tolerance, history,
             lower_bound, best_value, witness, decode, verify, goal=None):
    """Best-bound subdivision of the only two shared continuous decisions.

    Weekly integrality stays local. A parent certificate applies to both
    children. A real weekly schedule reconstructs in clock time independently
    of the node; its audited full-period bill is a global upper bound.
    """
    pending=[]
    serial=0
    records=[]
    leaves=[]
    heappush(pending,(lower_bound,serial,bounds,m,history))
    while pending:
        inherited,_,box,parent,previous=heappop(pending)
        if best_value-inherited<=tolerance or (goal is not None and inherited>=goal):
            leaves.append(inherited)
            continue
        ul,uh,wl,wh=box
        local=deepcopy(parent)
        local.lower[u],local.upper[u]=ul,uh
        local.add([(w,1),(u,-wl)],low=0)
        local.add([(w,1),(u,-wh)],high=0)
        target=min(goal,best_value) if goal is not None else best_value
        cutoff=target if goal is not None else target-.75*tolerance
        projected,extrema=_competitive_box(local,u,w,box,numerator,cutoff,port_constant)
        leaves.append(cutoff)
        if projected is None:
            records.append(dict(box=box,cutoff=cutoff,excluded_by_master_lp=True))
            continue
        box=projected
        ul,uh,wl,wh=box
        local.lower[u],local.upper[u]=ul,uh
        local.add([(w,1),(u,-wl)],low=0)
        local.add([(w,1),(u,-wh)],high=0)
        local.cost=numerator.copy()
        local.cost[u]-=target
        corners=[(a,a*b) for a in (ul,uh) for b in (wl,wh)]
        port_span=50./ul-50./uh
        scale=port_span+(wh-wl)
        fraction=min(.12,.05*scale)
        try:
            residual,proof,values,denominators=_weekly_support(
                local,owners,u,w,numerator,-port_constant,integer,tolerance*ul/16,
                fraction,previous,corners,capped=True)
        except _EmptyBox as exc:
            records.append(dict(box=box,lp_infeasible=str(exc)))
            continue
        r=residual+port_constant
        lower=max(inherited,target+r/(ul if r<0 else uh)-1e-7)
        records.append(dict(box=box,projected_extrema=extrema,lower=lower,trial=target,pricing=proof))
        if values is not None:
            trial=decode(values,denominators)
            trial,cost=verify(trial,best_value)
            if cost<best_value:
                witness,best_value=trial,cost
        if best_value-lower<=tolerance or (goal is not None and lower>=goal):
            leaves.append(lower)
            continue
        # The two widths are compared in physical metered kW. Split at an
        # interior midpoint so both closed children cover the parent.
        if port_span>=wh-wl:
            middle=(ul+uh)/2
            children=[(ul,middle,wl,wh),(middle,uh,wl,wh)]
            if not ul<middle<uh:
                raise ArithmeticError(("unsplit port meter interval",box,lower,best_value))
        else:
            middle=(wl+wh)/2
            children=[(ul,uh,wl,middle),(ul,uh,middle,wh)]
            if not wl<middle<wh:
                raise ArithmeticError(("unsplit warehouse meter interval",box,lower,best_value))
        column_history=previous+[proof] if len(proof)==len(set(owners.values())) and all(r["real"] for r in proof) else previous
        for child in children:
            serial+=1
            heappush(pending,(lower,serial,child,local,column_history))
    if not leaves:
        raise ArithmeticError("No certified region contains the incumbent")
    overall=min(leaves)
    if overall>best_value+1e-6:
        raise ArithmeticError(("spatial bound exceeds feasible cost",overall,best_value))
    return witness,best_value,overall,records


def _reservation_domains(m, reservations, objective, ceiling, count_sets=()):
    """Prove energy ranges in the cost sublevel set, reusing the simplex basis.

    The integer count can always be chosen minimal, ceil(energy / slot).
    If all such maxima fit in a group, its integer restriction is redundant.
    SciPy's pinned HiGHS distribution supplies the persistent LP interface.
    """
    start=perf_counter()
    cols=list(m.col)
    rows=list(m.row)
    values=list(m.data)
    for i,c in enumerate(objective):
        if c:
            cols.append(i)
            rows.append(len(m.lb))
            values.append(c)
    matrix=coo_matrix((values,(rows,cols)),shape=(len(m.lb)+1,len(m.cost))).tocsc()
    lp=highs_core.HighsLp()
    lp.num_col_,lp.num_row_=matrix.shape[1],matrix.shape[0]
    lp.a_matrix_.num_col_,lp.a_matrix_.num_row_=lp.num_col_,lp.num_row_
    lp.a_matrix_.format_=highs_core.MatrixFormat.kColwise
    lp.col_cost_=np.zeros(len(m.cost))
    lp.col_lower_,lp.col_upper_=m.lower,m.upper
    lp.row_lower_,lp.row_upper_=[*m.lb,-np.inf],[*m.ub,ceiling+1e-7]
    lp.a_matrix_.start_,lp.a_matrix_.index_,lp.a_matrix_.value_=matrix.indptr,matrix.indices,matrix.data
    solver=highs_core._Highs()
    solver.setOptionValue("output_flag",False)
    solver.setOptionValue("solver","simplex")
    solver.setOptionValue("primal_feasibility_tolerance",1e-8)
    solver.setOptionValue("dual_feasibility_tolerance",1e-8)
    if solver.passModel(lp)==highs_core.HighsStatus.kError:
        raise ArithmeticError("Failed to load reservation-domain LP")
    solved=0
    before=sum(m.integer)
    for count,slot_kwh,items in reservations:
        limits=[]
        for z,indices in items:
            extrema=[]
            for sign in (1.,-1.):
                for i in indices:
                    solver.changeColCost(i,sign)
                solver.run()
                if solver.getModelStatus()!=highs_core.HighsModelStatus.kOptimal:
                    raise ArithmeticError(("reservation-domain LP",solver.modelStatusToString(solver.getModelStatus())))
                extrema.append(sign*solver.getInfo().objective_function_value)
                solved+=1
            for i in indices:
                solver.changeColCost(i,0.)
            low,high=extrema
            n_min=max(0,ceil((low-1e-6)/slot_kwh)) if slot_kwh else int(low>1e-6)
            n_max=min(count,ceil((high+1e-6)/slot_kwh)) if slot_kwh else 1
            limits.append((z,n_min,n_max))
            if n_min>n_max:
                raise ArithmeticError(("reservation bounds",extrema,n_min,n_max))
            m.lower[z],m.upper[z]=n_min,n_max
            solver.changeColBounds(z,n_min,n_max)
            if n_min==n_max:
                m.integer[z]=False
        if slot_kwh and sum(hi for _,_,hi in limits)<=count:
            for z,_,_ in limits:
                m.integer[z]=False
    added=0
    # True quarter counts are integers, including counts whose integrality
    # was redundant within one block. Rounding a certified lower bound for
    # their sum strengthens the relaxation across windows and trip dates.
    for items in count_sets:
        if len(items)<2:
            continue
        for z in items:
            solver.changeColCost(z,1.)
        solver.run()
        if solver.getModelStatus()!=highs_core.HighsModelStatus.kOptimal:
            raise ArithmeticError(("reservation sum LP",solver.modelStatusToString(solver.getModelStatus())))
        raw=solver.getInfo().objective_function_value
        solved+=1
        for z in items:
            solver.changeColCost(z,0.)
        rounded=ceil(raw-1e-6)
        if rounded > raw+1e-6:
            m.add([(z,1) for z in items],low=rounded)
            solver.addRow(rounded,np.inf,len(items),np.asarray(items,dtype=np.int32),np.ones(len(items)))
            added+=1
    return dict(optimal_lp_count=solved,integer_before=before,integer_after=sum(m.integer),
                count_sum_cuts=added,seconds=perf_counter()-start)


def solve_port(p, equipment, spec, rule, active, energy_weight, weights, site_weights,
               upper_cost, domain, absolute_gap, incumbent=None, lower_target=None):
    from .cabinet_model import _bounded_mip, _groups
    started = perf_counter()
    scale = 50.
    port_lo, port_hi = domain["lower_kw"]["PORT"], domain["upper_kw"]["PORT"]
    wh_lo, wh_hi = domain["lower_kw"]["WAREHOUSE"], domain["upper_kw"]["WAREHOUSE"]
    if equipment != "one" or not 0 < port_lo <= port_hi <= scale or spec.truck_kw != scale:
        raise ValueError("E1 normalization requires a positive proven port peak and a 50 kW port")
    m = Matrix()
    u_min, u_max = scale/port_hi, scale/port_lo
    u = m.var(u_min,u_max)
    warehouse_peak = m.var(0,wh_hi*u_max,weights["WAREHOUSE"])
    m.add([(warehouse_peak,1),(u,-wh_lo)],low=0)
    m.add([(warehouse_peak,1),(u,-wh_hi)],high=0)
    case_by_day = {d:subset_case(case,[v for v in case["trucks"] if (d,v) in active])
                   for d,case in p.cases.items()}
    cap,reserve,e0 = spec.capacity_kwh,spec.reserve_kwh,spec.boundary_kwh
    levels = {}
    owners={}
    from .energy_boundary import components
    connected=components(p.days,p.links) if all("week_start" in d for d in p.days) else [p.days]
    by_date={d["date"]:group[0]["date"] for group in connected for d in group}
    for key in sorted(active):
        x,y = m.var(0,cap*u_max),m.var(0,cap*u_max)
        for state in (x,y):
            m.add([(state,1),(u,-cap)],high=0)
        levels[key] = x,y
        owners[x]=owners[y]=by_date[key[0]]
    for chain in p.chains:
        for j,key in enumerate(chain):
            if key not in active:
                continue
            x,y = levels[key]
            if rule==A or j==0 or chain[j-1] not in active:
                m.add([(x,1),(u,-e0)],0,0)
            else:
                m.add([(x,1),(levels[chain[j-1]][1],-1)],0,0)
            if rule==A or j+1==len(chain) or chain[j+1] not in active:
                m.add([(y,1),(u,-e0)],0,0)
    charged = defaultdict(list)
    groups = []
    reservation_groups=[]
    dated_counts=defaultdict(list)
    for d,case in case_by_day.items():
        begin_vars=len(m.cost)
        for site in SITES:
            for count,parts in _groups(case,site,flat=energy_weight==0):
                eligible = sorted({v for _,_,vs in parts for v in vs})
                # The warehouse usually has a single vehicle; then its entire
                # homogeneous group uses one continuous sum-of-quarters bound.
                if len(parts)==1 and (site=="PORT" or len(eligible)==1):
                    a,b,vs = parts[0]
                    hours = (b-a)/60
                    reservations = {}
                    decisions = []
                    for v in vs:
                        cost = energy_weight*p.prices[d][int(a//60)]/1000 + site_weights.get(site,0)
                        ub = (scale if site=="PORT" else scale*u_max)*hours*count
                        i = m.var(0,ub,cost)
                        charged[d,v].append((b+15*(count-1),i))
                        decisions.append((a,b,v,i))
                        if site=="PORT" and len(eligible)>1:
                            z = m.var(0,count,integer=True)
                            reservations[v] = z
                            m.add([(i,1),(z,-scale*hours)],-scale*hours,0)
                    if reservations:
                        m.add([(z,1) for z in reservations.values()],high=count)
                        reservation_groups.append((count,scale*hours,
                                                   [(reservations[v],[i]) for _,_,v,i in decisions]))
                        for v,z in reservations.items():
                            dated_counts[d,v,site].append((a,p.prices[d][int(a//60)],z))
                    if decisions:
                        all_energy = [(i,1) for _,_,_,i in decisions]
                        if site=="PORT":
                            m.add(all_energy,high=scale*hours*count)
                        else:
                            m.add(all_energy+[(u,-scale*hours*count)],high=0)
                            m.add(all_energy+[(warehouse_peak,-hours*count)],high=0)
                    groups.append((d,site,count,reservations,decisions))
                    continue
                for j in range(count):
                    reservations = ({v:m.var(0,1,integer=True) for v in eligible} if len(eligible)>1 else {})
                    if reservations:
                        m.add([(z,1) for z in reservations.values()],high=1)
                    metered,decisions = [],[]
                    for left,right,vs in parts:
                        a,b=left+15*j,right+15*j
                        hours=(b-a)/60
                        row=[]
                        for v in vs:
                            cost=energy_weight*p.prices[d][int(a//60)]/1000+site_weights.get(site,0)
                            i=m.var(0,scale*u_max*hours,cost)
                            row.append((i,1))
                            charged[d,v].append((b,i))
                            decisions.append((a,b,v,i))
                            if reservations:
                                m.add([(i,1),(reservations[v],-scale*u_max*hours)],high=0)
                        if row:
                            m.add(row+[(u,-scale*hours)],high=0)
                            metered.extend(row)
                    if site=="PORT":
                        m.add(metered,high=scale*.25)
                    else:
                        m.add(metered+[(warehouse_peak,-.25)],high=0)
                    if reservations:
                        reservation_groups.append((1,0,[(z,[i for _,_,truck,i in decisions if truck==v])
                                                         for v,z in reservations.items()]))
                        for v,z in reservations.items():
                            dated_counts[d,v,site].append((parts[0][0]+15*j,p.prices[d][int(parts[0][0]//60)],z))
                    groups.append((d,site,1,{},decisions))
        for v,task in case["trucks"].items():
            x,y = levels[d,v]
            previous,draw = x,0.
            cursor=0
            pieces = sorted(charged[d,v])
            for a,b,kwh,_ in task["trips"]:
                departure=m.var(0,cap*u_max)
                terms=[(previous,1),(u,-draw),(departure,-1)]
                while cursor < len(pieces) and pieces[cursor][0]<=a:
                    terms.append((pieces[cursor][1],spec.efficiency))
                    cursor += 1
                m.add(terms,0,0)
                for debit in (0.,kwh):
                    m.add([(departure,1),(u,-(debit+reserve))],low=0)
                    m.add([(departure,1),(u,-(debit+cap))],high=0)
                previous,draw=departure,kwh
            m.add([(previous,1),(u,-draw),(y,-1)]
                  +[(i,spec.efficiency) for _,i in pieces[cursor:]],0,0)
        owners.update({i:by_date[d] for i in range(begin_vars,len(m.cost))})

    # N/u is the annual physical bill, where N includes the constant port
    # meter term. For trial T, min(N-T*u) gives a global lower bound on F*.
    numerator = m.cost.copy()
    port_constant = weights["PORT"]*scale
    target = upper_cost
    steps=[]
    tolerance = absolute_gap if absolute_gap is not None else 1e-7
    lower_bound = float("-inf")
    preprocessing=None
    count_sets=set()
    for (d,v,site),entries in dated_counts.items():
        subsets=[entries]
        for left,right,s in case_by_day[d]["trucks"][v]["windows"]:
            if s==site:
                subsets.append([item for item in entries if left-15 < item[0] < right])
        for items in subsets:
            if len(items)<2:
                continue
            count_sets.add(tuple(sorted(item[2] for item in items)))
            cheap=sorted(items,key=lambda x:x[1])
            for n in (2,4,8,16,32):
                if n<len(cheap):
                    count_sets.add(tuple(sorted(item[2] for item in cheap[:n])))
    if rule!=A:
        # Carry-over fixes the grid demand of each uninterrupted served
        # vehicle chain even where no individual date fixes it. Count cuts
        # on its cheap port slots can therefore bind across midnight.
        for chain in p.chains:
            run=[]
            for key in [*chain,None]:
                if key in active:
                    run.append(key)
                    continue
                if len(run)>1:
                    items=[item for day,v in run for item in dated_counts[day,v,"PORT"]]
                    if len(items)>1:
                        count_sets.add(tuple(sorted(item[2] for item in items)))
                        cheap=sorted(items,key=lambda item:item[1])
                        for n in (2,4,8,16,32,64,128):
                            if n<len(cheap):
                                count_sets.add(tuple(sorted(item[2] for item in cheap[:n])))
                run=[]
    m.reservations=reservation_groups
    active_groups=set()
    original_integer=None
    support_records=[]
    best_witness=incumbent
    best_value=upper_cost
    if incumbent is not None:
        from .cabinet_audit import replay
        best_value=_bill(p,incumbent["schedule"],energy_weight,site_weights,weights)
        replay(p,equipment,spec,rule,{**incumbent,"stats":{"objective":best_value}},fixed=active,
               energy_weight=energy_weight,peak_weights=weights,site_energy_weights=site_weights)
        if best_value>upper_cost+1e-6:
            raise ValueError(("incumbent exceeds submitted ceiling",best_value,upper_cost))
    reference=(_schedule_columns(p,best_witness,by_date,energy_weight,site_weights) if best_witness else [])
    polished=set()
    polish_records=[]
    def consider(witness,current_best):
        from .cabinet_audit import replay
        value=_bill(p,witness["schedule"],energy_weight,site_weights,weights)
        if not site_weights and energy_weight:
            pattern=frozenset((r["site"],r["reservation_slot"],r["vehicle_id"]) for r in witness["schedule"])
            if pattern not in polished:
                from .cabinet_incumbent import polish_e1
                polished.add(pattern)
                alternative=polish_e1(p,spec,rule,active,witness,energy_weight,weights)
                info=alternative["stats"]
                polish_records.append({k:info.get(k) for k in ("status","status_code","objective","dual_bound","gap")})
                other=_bill(p,alternative["schedule"],energy_weight,site_weights,weights)
                if other<value:
                    value=other
                    witness={k:alternative[k] for k in ("schedule","states")}
        if value<current_best:
            replay(p,equipment,spec,rule,{**witness,"stats":{"objective":value}},
                   fixed=active,energy_weight=energy_weight,peak_weights=weights,site_energy_weights=site_weights)
        return witness,value

    if lower_target is not None and incumbent is not None and len(set(owners.values()))>1:
        # The target is a decision threshold, never an assumed feasible E1
        # budget. The capped oracle retains a zero-service artificial option.
        m.cost=numerator.copy()
        m.cost[u]-=lower_target
        corners=[(uu,ww*uu) for uu in (u_min,u_max) for ww in (wh_lo,wh_hi)]
        residual,proof,_,_=_weekly_support(m,owners,u,warehouse_peak,numerator,-port_constant,
                                           m.integer,tolerance*u_min/24,.15,[],corners,capped=True)
        residual+=port_constant
        lower_bound=max(lower_bound,lower_target+residual/(u_min if residual<0 else u_max)-1e-8)
        if lower_bound>=lower_target-1e-8:
            return {**incumbent,"stats":dict(status="Auxiliary lower bound certified",status_code=0,
                    objective=best_value,dual_bound=lower_bound,gap=max(0.,best_value-lower_bound)/max(1.,abs(best_value)),
                    requested_lower=lower_target,seconds=perf_counter()-started,weekly_bounds=proof,
                    meter_domain_support=domain["supports"])}
    while True:
        m.cost = numerator.copy()
        m.cost[u] -= target
        if preprocessing is None:
            preprocessing=_reservation_domains(m,reservation_groups,m.cost,-port_constant,
                                              sorted(count_sets,key=lambda k:(len(k),k)))
            original_integer=m.integer.copy()
            m.integer=[False]*len(m.integer)
            if len(set(owners.values()))>1:
                corners=[(uu,ww*uu) for uu in (u_min,u_max) for ww in (wh_lo,wh_hi)]
                for fraction in (.025,.02,.012):
                    bound,record,witness_values,denoms=_weekly_support(
                        m,owners,u,warehouse_peak,numerator,-port_constant,original_integer,
                        tolerance*u_min/12,fraction,([reference]+support_records if reference and support_records else support_records),corners)
                    support_records.append(record)
                    residual=bound+port_constant
                    certified=target+residual/(u_min if residual<0 else u_max)
                    lower_bound=max(lower_bound,certified)
                    witness=_decode(p,groups,levels,witness_values,by_date,denoms)
                    witness,value=consider(witness,best_value)
                    if value<best_value:
                        best_value,best_witness=value,witness
                        reference=_schedule_columns(p,witness,by_date,energy_weight,site_weights)
                    if lower_bound>best_value+1e-6:
                        raise ArithmeticError(("weekly lower bound exceeds feasible upper",lower_bound,best_value))
                    target_proven=lower_target is not None and lower_bound>=lower_target
                    if best_witness is not None and (best_value-lower_bound<=tolerance+1e-7 or target_proven):
                        return {**best_witness,"stats":dict(status=("Auxiliary lower bound certified" if target_proven
                            else "Optimal within absolute objective tolerance"),
                                status_code=0,objective=best_value,dual_bound=lower_bound,
                                gap=max(0.,best_value-lower_bound)/max(1.,abs(best_value)),
                                seconds=perf_counter()-started,weekly_support=support_records,reservation_polishing=polish_records,
                                reservation_domains=preprocessing,meter_domain_support=domain["supports"])}
                    target=best_value
                    m.cost[u]=-target
                if best_witness is not None:
                    decoded=lambda vals,den:_decode(p,groups,levels,vals,by_date,den)
                    witness,value,bound,regions=_spatial(
                        m,owners,u,warehouse_peak,numerator,original_integer,(u_min,u_max,wh_lo,wh_hi),
                        port_constant,tolerance,([reference]+support_records if reference else support_records),
                        lower_bound,best_value,best_witness,decoded,consider,lower_target)
                    return {**witness,"stats":dict(status=("Auxiliary lower bound certified" if lower_target is not None and
                             bound>=lower_target else "Optimal within absolute objective tolerance"),status_code=0,
                             objective=value,dual_bound=bound,gap=max(0.,value-bound)/max(1.,abs(value)),
                             seconds=perf_counter()-started,weekly_support=support_records,reservation_polishing=polish_records,
                             spatial_regions=regions,absolute_objective_tolerance=tolerance,
                             reservation_domains=preprocessing,meter_domain_support=domain["supports"])}
        tick=perf_counter()
        r=_bounded_mip(m,-port_constant+1e-7,tolerance*u_min*.5)
        if r.status != 0:
            raise ValueError(("fractional dispatch",r.message))
        denominator=float(r.x[u])
        objective=(sum(c*r.x[i] for i,c in enumerate(numerator) if c)+port_constant)/denominator
        native_bound=getattr(r,"mip_dual_bound",None)
        residual=(r.fun if native_bound is None else native_bound)+port_constant
        lower_bound=max(lower_bound,target+residual/(u_min if residual < 0 else u_max))
        if lower_bound>best_value+1e-6:
            raise ArithmeticError(("normalized lower bound exceeds feasible upper",lower_bound,best_value))
        steps.append(dict(status=r.message,status_code=r.status,objective=r.fun,
                          dual_bound=native_bound,gap=getattr(r,"mip_gap",None),
                          trial_value=target,physical_objective=objective,physical_lower_bound=lower_bound,
                          seconds=perf_counter()-tick))
        broken=set()
        for g,(count,slot,items) in enumerate(reservation_groups):
            amounts=[sum(r.x[i] for i in indices) for _,indices in items]
            used=(sum(max(0,ceil(amount/slot-1e-8)) for amount in amounts) if slot
                  else sum(amount>1e-8 for amount in amounts))
            if used>count:
                broken.add(g)
        steps[-1].update(active_groups=len(active_groups),unreconstructible_groups=len(broken))
        if broken:
            if active_groups & broken:
                raise ArithmeticError(("integer reservation replay",sorted(active_groups & broken)))
            for g in broken:
                for z,_ in reservation_groups[g][2]:
                    m.integer[z]=original_integer[z]
            active_groups.update(broken)
            continue
        if objective-lower_bound <= tolerance+1e-7:
            break
        if objective>=target-1e-9:
            raise ArithmeticError(("linear-fractional certificate stalled",steps[-1]))
        target=objective
    witness=_decode(p,groups,levels,r.x,by_date,dict.fromkeys(by_date.values(),denominator))
    stats=dict(status=r.message,status_code=r.status,objective=objective,dual_bound=lower_bound,
               gap=(objective-lower_bound)/max(1.,abs(objective)),seconds=perf_counter()-started,
               normalization_kw=scale,raw_linear_fractional_milps=steps,
               reservation_domains=preprocessing,
               weekly_support=support_records,
               meter_domain_support=domain["supports"],absolute_objective_tolerance=tolerance)
    return dict(stats=stats,**witness)
